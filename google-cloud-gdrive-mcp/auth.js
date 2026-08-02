import { google } from "googleapis";
import { readFileSync, writeFileSync } from "fs";
import * as readline from "readline";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required. Point it to a local Google OAuth JSON file outside git.`);
  }
  return value;
}

const credentialsPath = requiredEnv("GDRIVE_CREDENTIALS_PATH");
const tokenPath = requiredEnv("GDRIVE_TOKEN_PATH");
const credentials = JSON.parse(readFileSync(credentialsPath, "utf8"));
const { client_id, client_secret, redirect_uris } = credentials.installed || credentials.web;

const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);

const authUrl = oAuth2Client.generateAuthUrl({
  access_type: "offline",
  prompt: "consent",
  scope: ["https://www.googleapis.com/auth/drive"]
});

console.log("\nOpen this URL in your browser:\n");
console.log(authUrl);
console.log("\nAfter authorizing, paste the code here:");

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
rl.question("> ", async (code) => {
  const { tokens } = await oAuth2Client.getToken(code.trim());
  writeFileSync(tokenPath, JSON.stringify(tokens, null, 2), { mode: 0o600 });
  console.log(`\nToken saved to ${tokenPath}`);
  rl.close();
});
