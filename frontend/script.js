function login(){
  let name = document.getElementById("name").value;
  if(name === ""){
    alert("Enter name");
    return;
  }
  localStorage.setItem("name", name);
  window.location.href = "profile.html";
}

function next(){
  let role = document.getElementById("role").value;
  localStorage.setItem("role", role);
  window.location.href = "questions.html";
}

let role = JSON.parse(localStorage.getItem("patient"))?.role;

let questionsData = {

student: [
{q:"How frequently do you experience cognitive overload due to academic workload?", cat:"cognitive"},
{q:"Do you experience anticipatory anxiety before exams?", cat:"anxiety"},
{q:"How often does academic pressure disrupt your sleep cycle?", cat:"sleep"},
{q:"Do you wake up feeling mentally fatigued despite adequate rest?", cat:"sleep"},
{q:"Do you struggle to maintain focus during study sessions?", cat:"cognitive"},
{q:"Do deadlines trigger physiological stress responses?", cat:"anxiety"},
{q:"Do you feel emotionally drained due to academic expectations?", cat:"emotional"},
{q:"Do you experience persistent low mood related to studies?", cat:"emotional"},
{q:"Do you feel pressure to meet long-term career expectations?", cat:"cognitive"},
{q:"Do you experience burnout during exam periods?", cat:"emotional"},
{q:"Do distractions significantly reduce your productivity?", cat:"cognitive"},
{q:"Do you feel dissatisfied with your academic performance?", cat:"emotional"},
{q:"Do you feel mentally relaxed during your day?", cat:"emotional"},
{q:"Do you feel physically exhausted after studying?", cat:"sleep"},
{q:"Do you feel mentally overloaded most of the day?", cat:"cognitive"}
],

working: [
{q:"Do you experience sustained workload pressure during work hours?", cat:"cognitive"},
{q:"Do deadlines trigger anxiety or stress responses?", cat:"anxiety"},
{q:"Does work stress interfere with your sleep quality?", cat:"sleep"},
{q:"Do you wake up feeling fatigued despite sufficient rest?", cat:"sleep"},
{q:"Do you find it difficult to focus due to workload?", cat:"cognitive"},
{q:"Do workplace expectations create mental strain?", cat:"anxiety"},
{q:"Do you feel emotionally drained after work?", cat:"emotional"},
{q:"Do you experience low motivation related to work?", cat:"emotional"},
{q:"Do you feel overwhelmed by responsibilities?", cat:"cognitive"},
{q:"Do you experience burnout symptoms frequently?", cat:"emotional"},
{q:"Does stress reduce your productivity?", cat:"cognitive"},
{q:"Do you feel undervalued at work?", cat:"emotional"},
{q:"Do you feel mentally calm during work hours?", cat:"emotional"},
{q:"Do you feel physically exhausted after work?", cat:"sleep"},
{q:"Do you feel mentally overloaded throughout the day?", cat:"cognitive"}
],

home: [
{q:"Do household responsibilities feel overwhelming?", cat:"cognitive"},
{q:"Do you experience stress due to family expectations?", cat:"anxiety"},
{q:"Does stress affect your sleep quality?", cat:"sleep"},
{q:"Do you wake up feeling tired or unrested?", cat:"sleep"},
{q:"Do you struggle to manage multiple responsibilities?", cat:"cognitive"},
{q:"Do expectations create mental pressure?", cat:"anxiety"},
{q:"Do you feel emotionally unsupported?", cat:"emotional"},
{q:"Do you feel low or demotivated?", cat:"emotional"},
{q:"Do you feel overwhelmed with daily routine?", cat:"cognitive"},
{q:"Do you feel burnout from repetitive tasks?", cat:"emotional"},
{q:"Does stress reduce your efficiency?", cat:"cognitive"},
{q:"Do you feel unrecognized for your efforts?", cat:"emotional"},
{q:"Do you feel mentally calm during the day?", cat:"emotional"},
{q:"Do you feel physically exhausted daily?", cat:"sleep"},
{q:"Do you feel mentally overloaded often?", cat:"cognitive"}
]

};

let questions = questionsData[role] || [];
let index = 0;
let answers = [];

if(document.getElementById("question")){
  load();
}

function load(){
  document.getElementById("question").innerText =
  "Q" + (index+1) + ". " + questions[index].q;
}

function answer(val){

  answers.push(val);
  index++;

  if(index < questions.length){
    load();
  } else {
    calc();
  }
}

function calc(){

fetch("https://hpalytics-healthcare.onrender.com/submit"),{
  method:"POST",
  headers:{
    "Content-Type":"application/json"
  },
  body: JSON.stringify({
  answers: answers,
  user: JSON.parse(localStorage.getItem("patient"))
})
}
.then(res => res.json())
.then(data => {

  console.log("DATA:", data);

  if(!data || !data.score){
    alert("Server data problem");
    return;
  }

  localStorage.setItem("score", data.score || 0);
  localStorage.setItem("result", data.level || "Unknown");
  localStorage.setItem("report", data.report || "No report");
  localStorage.setItem("breakdown", JSON.stringify(data.breakdown || {}));
  localStorage.setItem("remedies", JSON.stringify(data.remedies || []));

  window.location.href = "result.html";

})

}

// ================= RESULT =================

if(document.getElementById("score")){

  let score = localStorage.getItem("score") || "0";
  let level = localStorage.getItem("result") || "N/A";
  let report = localStorage.getItem("report") || "No report available";

  document.getElementById("score").innerText = score;
  document.getElementById("level").innerText = level;
  document.getElementById("report").innerText = report;

  let remedies = JSON.parse(localStorage.getItem("remedies") || "[]");

  let container = document.getElementById("remedies");

  remedies.forEach(r=>{
    let div = document.createElement("div");
    div.className = "card p-3 mt-3";

    let html = `<h6>${r.title}</h6><ul>`;
    r.details.forEach(d=>{
      html += `<li>${d}</li>`;
    });
    html += "</ul>";

    div.innerHTML = html;
    container.appendChild(div);
  });

}

// ================= PDF =================

async function downloadPDF(){

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();

  let patient = JSON.parse(localStorage.getItem("patient")) || {};

  let score = localStorage.getItem("score") || "0";
  let level = localStorage.getItem("result") || "N/A";
  let report = localStorage.getItem("report") || "";

  doc.setFontSize(16);
  doc.text("HPAlytics Clinical Report", 20, 20);

  doc.setFontSize(12);

  doc.text("Patient Details:", 20, 40);

  doc.text("Name: " + (patient.name || "N/A"), 20, 50);
  doc.text("Age: " + (patient.age || "N/A"), 20, 60);
  doc.text("Gender: " + (patient.gender || "N/A"), 20, 70);
  doc.text("Phone: " + (patient.phone || "N/A"), 20, 80);
  doc.text("Email: " + (patient.email || "N/A"), 20, 90);
  doc.text("Occupation: " + (patient.role || "N/A"), 20, 100);

  doc.text("Assessment Result:", 20, 120);
  doc.text("Stress Level: " + level, 20, 130);
  doc.text("Score: " + score, 20, 140);

  doc.text("Clinical Interpretation:", 20, 160);
  doc.text(report, 20, 170, { maxWidth: 160 });

  doc.save("Patient_Report.pdf");
}

function savePatient(){

  let patient = {
    name: document.getElementById("name").value.trim(),
    age: document.getElementById("age").value.trim(),
    gender: document.getElementById("gender").value,
    phone: document.getElementById("phone").value.trim(),
    email: document.getElementById("email").value.trim(),
    role: document.getElementById("role").value
  };

  console.log("PATIENT DATA:", patient); // 🔥 debug

  if(!patient.name || !patient.age || !patient.phone || !patient.email){
    alert("Fill all details properly da 😏");
    return;
  }

  localStorage.setItem("patient", JSON.stringify(patient));

  window.location.href = "questions.html";
}