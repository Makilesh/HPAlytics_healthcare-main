const express = require("express");
const cors = require("cors");
const mongoose = require("mongoose");


const app = express();
app.use(cors());
app.use(express.json());

// ================= DB CONNECTION =================
mongoose.connect(process.env.MONGO_URI)
.then(()=>console.log("🟢 MongoDB Connected"))
.catch(err=>console.log("🔴 DB Error:", err));

// ================= SCHEMA =================
const patientSchema = new mongoose.Schema({
  name: String,
  age: String,
  gender: String,
  phone: String,
  email: String,
  role: String,
  answers: Array,
  score: Number,
  level: String,
  breakdown: Object,
  report: String,
  remedies: Array,
  createdAt: {
    type: Date,
    default: Date.now
  }
});

const Patient = mongoose.model("Patient", patientSchema);

// ================= MEMORY (optional debug) =================
let sessions = [];

// ================= POST /submit =================
app.post("/submit", async (req, res) => {
  try {
    const { answers, user } = req.body;

    if (!answers || !Array.isArray(answers) || answers.length === 0) {
      return res.status(400).json({ error: "No answers provided" });
    }

    // ================= SCORE =================
    const score = answers.reduce((a, b) => a + b, 0);

    // ================= BREAKDOWN =================
    const breakdown = {
      cognitive: (answers[0]||0)+(answers[4]||0)+(answers[8]||0)+(answers[10]||0),
      anxiety:   (answers[1]||0)+(answers[5]||0),
      emotional: (answers[6]||0)+(answers[7]||0)+(answers[9]||0)+(answers[11]||0)+(answers[12]||0),
      sleep:     (answers[2]||0)+(answers[3]||0)+(answers[13]||0),
    };

    // ================= LEVEL =================
    const w =
      breakdown.sleep*1.2 +
      breakdown.anxiety*1.5 +
      breakdown.emotional*1.4 +
      breakdown.cognitive*1.3;

    const level =
      w>60 || breakdown.anxiety>=8 ? "High" :
      w>35 ? "Moderate" : "Low";

    // ================= REPORT =================
    const REPORTS = {
      High:     "Elevated stress indicators detected across multiple psychometric dimensions. Patterns suggest heightened cortisol response and sympathetic nervous system activation. Immediate clinical consultation and structured intervention strongly recommended.",
      Moderate: "Moderate stress levels identified with notable patterns. Lifestyle adjustments, mindfulness-based stress reduction, and relaxation techniques are advised.",
      Low:      "Low stress levels detected. Indicates stable mental wellness and effective coping mechanisms."
    };

    // ================= REMEDIES =================
    const remedies = [];

    if (breakdown.sleep>5)
      remedies.push({
        title:"Sleep Regulation Protocol",
        icon:"💤",
        details:[
          "Maintain consistent 7–8 hour sleep schedule",
          "Avoid screens before bedtime",
          "Limit caffeine intake after 2 PM",
          "Practice guided relaxation before sleep"
        ]
      });

    if (breakdown.anxiety>5)
      remedies.push({
        title:"Anxiety Management Plan",
        icon:"🧘",
        details:[
          "Practice deep breathing (4-7-8)",
          "Reduce overthinking triggers",
          "Daily mindfulness (10 mins)",
          "Break tasks into smaller goals"
        ]
      });

    if (breakdown.emotional>8)
      remedies.push({
        title:"Emotional Stability Strategy",
        icon:"💛",
        details:[
          "Daily journaling",
          "Talk to trusted person",
          "Music therapy",
          "Spend time in nature"
        ]
      });

    if (breakdown.cognitive>8)
      remedies.push({
        title:"Cognitive Focus Plan",
        icon:"🧩",
        details:[
          "Use Pomodoro technique",
          "Avoid multitasking",
          "Prioritize tasks",
          "Take regular breaks"
        ]
      });

    if (!remedies.length)
      remedies.push({
        title:"Wellness Maintenance",
        icon:"🌿",
        details:[
          "Maintain physical activity",
          "Social interaction",
          "Digital detox",
          "Routine check-ups"
        ]
      });

    // ================= SAVE TO DB 🔥 =================
    await Patient.create({
      ...user,
      answers,
      score,
      level,
      breakdown,
      report: REPORTS[level],
      remedies
    });

    // ================= MEMORY STORE =================
    sessions.push({
      ts: new Date().toISOString(),
      user,
      score,
      level,
      breakdown
    });

    // ================= RESPONSE =================
    res.json({
      score,
      level,
      report: REPORTS[level],
      breakdown,
      remedies
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Internal server error" });
  }
});

// ================= DEBUG ROUTES =================
app.get("/sessions", (req, res) => res.json({ count: sessions.length, sessions }));
app.get("/patients", async (req, res) => {
  try {
    const data = await Patient.find().sort({ createdAt: -1 });
    res.json(data);
  } catch (err) {
    console.error("PATIENT FETCH ERROR:", err);
    res.status(500).json({ error: "Failed to fetch patients" });
  }
});

app.get("/health", (req, res) =>
  res.json({ status:"ok", uptime: process.uptime() })
);

app.get("/", (req, res) => {
  res.send("🚀 HPAlytics Backend Running Successfully");
});
// ================= START =================
const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(`\n🧠 MindPulse Server → http://localhost:${PORT}`);
  console.log(`📋 Sessions         → http://localhost:${PORT}/sessions`);
  console.log(`🗄 Patients (DB)    → http://localhost:${PORT}/patients`);
  console.log(`✅ Health           → http://localhost:${PORT}/health\n`);
});