import { google } from "googleapis";
import { readFileSync, writeFileSync } from "fs";

function log(message) {
  console.log(`${new Date().toISOString()} ${message}`);
}

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required. Point it to a local Google OAuth JSON file outside git.`);
  }
  return value;
}

const credentialsPath = requiredEnv("GDRIVE_CREDENTIALS_PATH");
const tokenPath = requiredEnv("GDRIVE_TOKEN_PATH");

try {
  const credentials = JSON.parse(readFileSync(credentialsPath, "utf8"));
  const { client_id, client_secret, redirect_uris } = credentials.installed || credentials.web;
  const token = JSON.parse(readFileSync(tokenPath, "utf8"));

  const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);
  oAuth2Client.setCredentials(token);
  oAuth2Client.on("tokens", (tokens) => {
    const nextToken = { ...oAuth2Client.credentials, ...tokens };
    if (!nextToken.refresh_token && token.refresh_token) {
      nextToken.refresh_token = token.refresh_token;
    }
    writeFileSync(tokenPath, JSON.stringify(nextToken, null, 2), { mode: 0o600 });
  });

  await oAuth2Client.getAccessToken();

  const drive = google.drive({ version: "v3", auth: oAuth2Client });
  await drive.files.list({
    pageSize: 1,
    fields: "files(id,name)"
  });

  log(`Google Drive token OK; expiry=${oAuth2Client.credentials.expiry_date || "unknown"}`);
} catch (error) {
  const googleError = error?.response?.data?.error || error?.code;
  const googleDescription = error?.response?.data?.error_description;
  log(`Google Drive token refresh FAILED: ${googleError || error?.message || String(error)} ${googleDescription || ""}`.trim());
  process.exit(1);
}
