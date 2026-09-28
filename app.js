const API = window.VOICE_API_BASE || "";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const languages = [
  ["en","🇺🇸","English"],["hi","🇮🇳","Hindi"],["es","🇪🇸","Spanish"],["fr","🇫🇷","French"],["de","🇩🇪","German"],
  ["it","🇮🇹","Italian"],["pt","🇵🇹","Portuguese"],["ja","🇯🇵","Japanese"],["ko","🇰🇷","Korean"],["zh","🇨🇳","Chinese"],
  ["ar","🇸🇦","Arabic"],["nl","🇳🇱","Dutch"],["ru","🇷🇺","Russian"],["tr","🇹🇷","Turkish"],["pl","🇵🇱","Polish"],
  ["sv","🇸🇪","Swedish"],["da","🇩🇰","Danish"],["fi","🇫🇮","Finnish"],["el","🇬🇷","Greek"],["he","🇮🇱","Hebrew"],
  ["ms","🇲🇾","Malay"],["no","🇳🇴","Norwegian"],["sw","🇹🇿","Swahili"]
];

let selectedLanguage = "en";
let referenceFile = null;
let currentJob = null;
let pollTimer = null;

function wordCount(text){ return (text.trim().match(/\S+/g)||[]).length; }
function showAlert(msg, type=""){ const el=$("#alert"); el.textContent=msg; el.className=`alert ${type}`; el.classList.remove("hidden"); }
function hideAlert(){ $("#alert").classList.add("hidden"); }

function renderLanguages(){
  $("#languageGrid").innerHTML = languages.map(([code,flag,name])=>`
    <button class="lang ${code===selectedLanguage?"selected":""}" data-lang="${code}" type="button">
      <span>${flag}</span><b>${name}</b><small>${code.toUpperCase()}</small>
    </button>`).join("");
  $$(".lang").forEach(b=>b.addEventListener("click",()=>{selectedLanguage=b.dataset.lang;renderLanguages();}));
}

function updateWords(){
  const text=$("#script").value, n=wordCount(text);
  $("#wordCount").textContent=`${n.toLocaleString()} / 10,000`;
  $("#charCount").textContent=`${text.length.toLocaleString()} characters`;
  $("#wordCount").style.color = n>10000 ? "#e47f76" : "";
}

function setControl(id,out,fmt){ const el=$("#"+id); const o=$("#"+out); const update=()=>o.textContent=fmt(Number(el.value)); el.addEventListener("input",update); update(); }
setControl("speed","speedOut",v=>`${v.toFixed(2)}×`);
setControl("stability","stabilityOut",v=>`${Math.round(v*100)}%`);
setControl("expressiveness","expressOut",v=>`${Math.round(v*100)}%`);
setControl("temperature","tempOut",v=>v.toFixed(2));
$("#script").addEventListener("input",updateWords);

$$(".presets button").forEach(b=>b.addEventListener("click",()=>{
  $$(".presets button").forEach(x=>x.classList.remove("selected")); b.classList.add("selected");
  const n=Number(b.dataset.limit);
  const words=wordCount($("#script").value);
  showAlert(`${n.toLocaleString()} words selected as the generation limit. The backend enforces a 10,000-word maximum.`, "");
  setTimeout(hideAlert,2500);
}));

const drop=$("#dropzone"), input=$("#voiceFile");
drop.addEventListener("click",()=>input.click());
["dragenter","dragover"].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add("drag")}));
["dragleave","drop"].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove("drag")}));
drop.addEventListener("drop",ev=>{ if(ev.dataTransfer.files[0]) handleFile(ev.dataTransfer.files[0]); });
input.addEventListener("change",()=>{if(input.files[0])handleFile(input.files[0])});

async function handleFile(file){
  const allowed=["audio/mpeg","audio/wav","audio/x-wav","audio/mp4","audio/x-m4a","audio/flac","audio/ogg"];
  const ext=file.name.toLowerCase().split(".").pop();
  if(!allowed.includes(file.type) && !["mp3","wav","m4a","flac","ogg"].includes(ext)){showAlert("Please choose an MP3, WAV, M4A, FLAC or OGG file.","error");return}
  if(file.size>50*1024*1024){showAlert("Reference audio must be under 50 MB.","error");return}
  referenceFile=file;
  $("#fileName").textContent=file.name;
  $("#fileInfo").textContent=`${(file.size/1024/1024).toFixed(2)} MB`;
  $("#filePreview").classList.remove("hidden");
  $("#voicePlayerWrap").classList.remove("hidden");
  $("#voicePlayer").src=URL.createObjectURL(file);
  $("#qualityBadge").textContent="Checking…"; $("#qualityBadge").className="badge";
  try{
    const fd=new FormData();fd.append("file",file);
    const r=await fetch(`${API}/api/analyze-reference`,{method:"POST",body:fd});
    const data=await r.json(); if(!r.ok)throw new Error(data.detail||"Audio analysis failed");
    $("#qualityBadge").textContent=`✓ ${data.quality}`;
    $("#qualityBadge").className="badge";
    showAlert(`Reference checked: ${data.duration}s normalized speech sample.`,`success`);
    setTimeout(hideAlert,3000);
  }catch(e){$("#qualityBadge").textContent="Ready";showAlert(e.message,"error")}
}
$("#removeFile").addEventListener("click",()=>{referenceFile=null;input.value="";$("#filePreview").classList.add("hidden");$("#voicePlayerWrap").classList.add("hidden");$("#qualityBadge").textContent="Not checked";$("#qualityBadge").className="badge muted"});
$("#themeBtn").addEventListener("click",()=>document.body.classList.toggle("light"));

function setProgress(p,msg){$("#progressBar").style.width=`${p}%`;$("#progressPct").textContent=`${p}%`;$("#progressMessage").textContent=msg;}
function setGenerating(on){
  $("#generateBtn").disabled=on; $("#progressArea").classList.toggle("hidden",!on);
  if(on){$("#generateText").textContent="Generating…";$("#generateBtn").querySelector(".spark").textContent="◌"}
  else{$("#generateText").textContent="Generate voice";$("#generateBtn").querySelector(".spark").textContent="✦"}
}

async function generate(){
  hideAlert();
  if(!referenceFile){showAlert("Upload a clear reference voice first.","error");return}
  const text=$("#script").value.trim(), words=wordCount(text);
  if(!words){showAlert("Enter your narration text.","error");return}
  if(words>10000){showAlert("The current maximum is 10,000 words per generation.","error");return}
  if(!$("#consent").checked){showAlert("Please confirm that you have permission to clone this voice.","error");return}

  const fd=new FormData();
  fd.append("reference",referenceFile);
  fd.append("language",selectedLanguage);
  fd.append("text",text);
  fd.append("speed",$("#speed").value);
  fd.append("stability",$("#stability").value);
  fd.append("expressiveness",$("#expressiveness").value);
  fd.append("temperature",$("#temperature").value);
  fd.append("consent","true");

  setGenerating(true);setProgress(0,"Uploading reference…");
  try{
    const r=await fetch(`${API}/api/generate`,{method:"POST",body:fd});
    const data=await r.json(); if(!r.ok)throw new Error(data.detail||"Generation request failed");
    currentJob=data.job_id; pollTimer=setInterval(pollJob,1200);
  }catch(e){setGenerating(false);showAlert(e.message,"error")}
}

async function pollJob(){
  if(!currentJob)return;
  try{
    const r=await fetch(`${API}/api/jobs/${currentJob}`);const d=await r.json();
    setProgress(d.progress||0,d.message||d.status);
    if(d.status==="completed"){
      clearInterval(pollTimer);setGenerating(false);setProgress(100,"Complete");
      $("#resultCard").classList.remove("hidden");
      $("#resultPlayer").src=API+d.mp3_url;
      $("#downloadMp3").href=API+d.mp3_url;
      $("#downloadWav").href=API+d.wav_url;
      addHistory(d);showAlert("Voice generation completed successfully.","success");
      $("#resultCard").scrollIntoView({behavior:"smooth",block:"center"});
    }else if(d.status==="error"){
      clearInterval(pollTimer);setGenerating(false);showAlert(d.message||"Generation failed.","error");
    }
  }catch(e){clearInterval(pollTimer);setGenerating(false);showAlert("Could not read generation status. Check the backend connection.","error")}
}

function addHistory(job){
  const arr=JSON.parse(localStorage.getItem("vf_history")||"[]");
  arr.unshift({id:currentJob,words:job.words||wordCount($("#script").value),chunks:job.chunks||0,time:new Date().toLocaleString(),mp3:job.mp3_url,wav:job.wav_url});
  localStorage.setItem("vf_history",JSON.stringify(arr.slice(0,12)));renderHistory();
}
function renderHistory(){
  const arr=JSON.parse(localStorage.getItem("vf_history")||"[]");
  $("#historyList").innerHTML=arr.length?arr.map(x=>`
    <div class="history-item"><div class="file-icon">♫</div><div class="mini"><b>${x.words.toLocaleString()} words • ${x.chunks} sections</b><span>${x.time}</span></div>
    <a class="btn" href="${API}${x.mp3}" download>MP3</a></div>`).join(""):`<div class="empty">No generations yet.</div>`;
}
$("#clearHistory").addEventListener("click",()=>{localStorage.removeItem("vf_history");renderHistory()});
$("#generateBtn").addEventListener("click",generate);
$("#newGeneration").addEventListener("click",()=>$("#studio").scrollIntoView({behavior:"smooth"}));

renderLanguages();updateWords();renderHistory();
