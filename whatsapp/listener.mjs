/**
 * The Doctor — WhatsApp Voice Note Listener
 *
 * Listens for voice notes from authorized contacts via WhatsApp,
 * transcribes them using the existing Perplexity bridge script,
 * and processes them through The Doctor's health data pipeline.
 *
 * Usage:
 *   npm start          # Start the listener
 *   npm run login      # Force re-login (clear saved session)
 *
 * First run: scan QR code with WhatsApp (Settings > Linked Devices)
 */

import pkg from "whatsapp-web.js";
const { Client, LocalAuth, MessageTypes } = pkg;
import qrcode from "qrcode-terminal";
import { config } from "dotenv";
import { execFile } from "node:child_process";
import { writeFile, unlink, mkdtemp } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// ── Config ──────────────────────────────────────────────────────────────

// Load test .env.test if DOCTOR_ENV=test, otherwise load production .env
const envFile = process.env.DOCTOR_ENV === "test" ? ".env.test" : ".env";
config({ path: join(import.meta.dirname, "..", envFile) });

const BRIDGE_SCRIPT = process.env.DOCTOR_BRIDGE_SCRIPT ||
  join(process.env.HOME, "Documents", "Development", "perplexity-stack", "scripts", "transcribe.py");

const BRIDGE_PYTHON = process.env.DOCTOR_BRIDGE_PYTHON ||
  join(process.env.HOME, "Documents", "Development", "perplexity-stack", "perplexity-web-wrapper", ".venv", "bin", "python3");

const DOCTOR_PROCESSOR = join(import.meta.dirname, "..", "processor.py");

// Allowed WhatsApp numbers (international format, no +)
// e.g., "491512345678" or leave empty to accept all
const ALLOWED_NUMBERS = (process.env.DOCTOR_WHATSAPP_ALLOWED || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const FORCE_LOGIN = process.argv.includes("--login");

// ── Helpers ─────────────────────────────────────────────────────────────

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] ${msg}`);
}

function waitForMessage(client, timeoutMs = 120_000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("QR scan timed out")), timeoutMs);
    client.once("ready", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

async function transcribeAudio(audioPath) {
  /** Call the Perplexity bridge script to transcribe an audio file */
  log("  🎤 Calling bridge script...");
  const { stdout, stderr } = await execFileAsync(BRIDGE_PYTHON, [BRIDGE_SCRIPT, audioPath], {
    timeout: 120_000,
    maxBuffer: 10 * 1024 * 1024,
  });

  if (stderr) log(`  ⚠️  Bridge stderr: ${stderr}`);

  const result = JSON.parse(stdout);
  const text = result?.text;
  if (!text) throw new Error("Bridge returned empty transcription");
  return text;
}

async function processWithDoctor(audioPath, recordingTime) {
  /** Run The Doctor's processor on the audio file for health extraction */
  log("  🏥 Running health extraction...");
  const { stdout, stderr } = await execFileAsync(BRIDGE_PYTHON, [
    DOCTOR_PROCESSOR, audioPath, "--time", recordingTime,
  ], {
    timeout: 180_000,
    maxBuffer: 10 * 1024 * 1024,
  });

  log(`  ✅ Health extraction complete`);
  // Return whether it succeeded (processor prints confirmation)
  return stdout.includes("Processing complete!");
}

// ── Main ────────────────────────────────────────────────────────────────

async function main() {
  log("=".repeat(50));
  log("🏥 The Doctor — WhatsApp Listener");
  log("=".repeat(50));
  log(`  Bridge: ${BRIDGE_SCRIPT}`);
  log(`  Python: ${BRIDGE_PYTHON}`);
  log(`  Processor: ${DOCTOR_PROCESSOR}`);

  if (ALLOWED_NUMBERS.length > 0) {
    log(`  Allowed numbers: ${ALLOWED_NUMBERS.join(", ")}`);
  } else {
    log("  ⚠️  No allowed numbers set — will accept all messages");
  }

  // ── Initialize WhatsApp client ──────────────────────────────────────

  const client = new Client({
    authStrategy: new LocalAuth({
      dataPath: join(import.meta.dirname, ".whatsapp-auth"),
    }),
    puppeteer: {
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  });

  // ── QR Code ─────────────────────────────────────────────────────────

  client.on("qr", (qr) => {
    log("📱 Scan QR code with WhatsApp (Settings > Linked Devices)");
    qrcode.generate(qr, { small: true });
  });

  // ── Ready ───────────────────────────────────────────────────────────

  client.on("ready", () => {
    log("✅ WhatsApp connected!");
    log("   Listening for voice notes...");
  });

  // ── Authentication failure ──────────────────────────────────────────

  client.on("auth_failure", (msg) => {
    log(`❌ Auth failure: ${msg}`);
    log("   Run: npm run login");
  });

  // ── Disconnected ────────────────────────────────────────────────────

  client.on("disconnected", (reason) => {
    log(`⚠️  Disconnected: ${reason}`);
    log("   Reconnecting...");
  });

  // ── Incoming messages ───────────────────────────────────────────────

  client.on("message", async (msg) => {
    try {
      // Only process voice notes
      if (msg.type !== MessageTypes.VOICE && msg.type !== MessageTypes.AUDIO) {
        return;
      }

      const contact = await msg.getContact();
      const fromNumber = msg.from.replace(/@c\.us$/, "");
      const pushName = contact.pushname || contact.name || fromNumber;

      log(`🎤 Voice note from ${pushName} (${fromNumber})`);

      // Authorization check
      if (ALLOWED_NUMBERS.length > 0 && !ALLOWED_NUMBERS.includes(fromNumber)) {
        log(`  ⛔ Unauthorized number: ${fromNumber}`);
        return;
      }

      // Check if it's from the bot itself
      const botNumber = client.info?.wid?.user;
      if (fromNumber === botNumber) return;

      await msg.reply("🔄 Processing your voice note...");

      // ── Download audio ────────────────────────────────────────────
      log("  💾 Downloading audio...");
      const media = await msg.downloadMedia();
      if (!media) {
        await msg.reply("❌ Could not download the audio.");
        return;
      }

      // Save to temp file
      const tmpDir = await mkdtemp(join(tmpdir(), "doctor-wa-"));
      const ext = media.mimetype?.includes("ogg") ? ".ogg" : ".mp3";
      const audioPath = join(tmpDir, `voice_${Date.now()}${ext}`);
      await writeFile(audioPath, media.data, "base64");

      log(`  💾 Saved: ${audioPath} (${(media.filesize || 0) / 1024} KB)`);

      // ── Transcribe ───────────────────────────────────────────────
      await msg.reply("🎤 Transcribing...");
      const transcription = await transcribeAudio(audioPath);
      log(`  ✅ Transcription (${transcription.length} chars)`);
      log(`     Preview: ${transcription.slice(0, 100)}...`);

      // ── Health extraction ────────────────────────────────────────
      const recordingTime = new Date(msg.timestamp * 1000)
        .toISOString()
        .slice(0, 19)
        .replace("T", " ");

      await msg.reply("🏥 Extracting health data...");
      const success = await processWithDoctor(audioPath, recordingTime);

      // ── Reply ────────────────────────────────────────────────────
      if (success) {
        const summary = transcription.length > 200
          ? transcription.slice(0, 200) + "..."
          : transcription;
        await msg.reply(
          `✅ Done!\n\n📝 ${summary}\n\n📊 Dashboard: http://localhost:9001`
        );
      } else {
        await msg.reply("✅ Transcribed! Health extraction running in background.");
      }

      log(`  ✅ Voice note processed successfully`);

      // Clean up
      await unlink(audioPath).catch(() => {});
    } catch (err) {
      log(`  ❌ Error: ${err.message}`);
      try {
        await msg.reply(`❌ Error: ${err.message.slice(0, 200)}`);
      } catch {}
    }
  });

  // ── Start ───────────────────────────────────────────────────────────

  log("\n🚀 Starting WhatsApp client...");
  log("   (Chrome will open in headless mode)\n");

  if (FORCE_LOGIN) {
    // Clear saved session to force fresh QR
    const { rm } = await import("node:fs/promises");
    const authPath = join(import.meta.dirname, ".whatsapp-auth");
    await rm(authPath, { recursive: true, force: true }).catch(() => {});
    log("   Session cleared. Fresh QR will appear on next start.");
  }

  client.initialize();
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
