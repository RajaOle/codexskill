import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { google } from "googleapis";
import { readFileSync, writeFileSync, createReadStream } from "fs";

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

const drive = google.drive({ version: "v3", auth: oAuth2Client });
const sheets = google.sheets({ version: "v4", auth: oAuth2Client });

function formatError(error) {
  const googleError = error?.response?.data?.error || error?.code;
  const googleDescription = error?.response?.data?.error_description;
  if (googleError === "deleted_client") {
    return "Google Drive authentication failed: OAuth client was deleted in Google Cloud. Create a new OAuth Desktop client, replace the credentials JSON, then run npm run auth again.";
  }
  if (googleError === "invalid_grant") {
    return "Google Drive authentication failed: refresh token is invalid or revoked. Run npm run auth again with the current credentials JSON.";
  }
  return `Google Drive MCP error: ${googleDescription || error?.message || String(error)}`;
}

const server = new Server(
  { name: "gdrive", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "list_files",
      description: "List or search files in Google Drive.",
      inputSchema: { type: "object", properties: { query: { type: "string" } } }
    },
    {
      name: "auth_status",
      description: "Check whether Google Drive OAuth credentials and token are currently valid.",
      inputSchema: { type: "object", properties: {} }
    },
    {
      name: "read_sheet",
      description: "Read ALL data from a Google Sheet by file ID.",
      inputSchema: { type: "object", properties: { fileId: { type: "string" } }, required: ["fileId"] }
    },
    {
      name: "read_sheet_range",
      description: "Read a specific range from a Google Sheet e.g. Sheet1!A1:Z100.",
      inputSchema: {
        type: "object",
        properties: { fileId: { type: "string" }, range: { type: "string" } },
        required: ["fileId", "range"]
      }
    },
    {
      name: "read_sheet_formula_range",
      description: "Read formulas from a specific Google Sheet range. Formula cells are returned as formulas; literal cells are returned as values.",
      inputSchema: {
        type: "object",
        properties: { fileId: { type: "string" }, range: { type: "string" } },
        required: ["fileId", "range"]
      }
    },
    {
      name: "write_sheet",
      description: "Write or append data to a Google Sheet. Use to update cells or append rows.",
      inputSchema: {
        type: "object",
        properties: {
          fileId: { type: "string", description: "Spreadsheet ID" },
          range: { type: "string", description: "Range like Sheet1!A2:E2" },
          values: {
            type: "array",
            description: "2D array of values e.g. [[col1, col2, col3]]",
            items: { type: "array" }
          },
          append: { type: "boolean", description: "If true, append rows instead of overwrite" }
        },
        required: ["fileId", "range", "values"]
      }
    },
    {
      name: "duplicate_sheet",
      description: "Duplicate a tab in a Google Spreadsheet, preserving formatting and formulas. Use this to create a new month from a previous month.",
      inputSchema: {
        type: "object",
        properties: {
          fileId: { type: "string", description: "Spreadsheet ID" },
          sourceSheetName: { type: "string", description: "Existing tab name to copy, e.g. April" },
          targetSheetName: { type: "string", description: "New tab name, e.g. Mei" }
        },
        required: ["fileId", "sourceSheetName", "targetSheetName"]
      }
    },
    {
      name: "upload_file",
      description: "Upload a local file to a Google Drive folder. Returns the file ID and shareable link.",
      inputSchema: {
        type: "object",
        properties: {
          localPath: { type: "string", description: "Local file path to upload" },
          fileName: { type: "string", description: "File name in Google Drive" },
          folderId: { type: "string", description: "Google Drive folder ID to upload into" },
          mimeType: { type: "string", description: "MIME type e.g. image/jpeg, image/png" }
        },
        required: ["localPath", "fileName"]
      }
    },
    {
      name: "get_folder_id",
      description: "Find a folder ID by name in Google Drive.",
      inputSchema: { type: "object", properties: { folderName: { type: "string" } }, required: ["folderName"] }
    }
  ]
}));

async function handleTool(req) {
  const { name, arguments: args = {} } = req.params;

  if (name === "auth_status") {
    await oAuth2Client.getAccessToken();
    return {
      content: [{
        type: "text",
        text: JSON.stringify({
          ok: true,
          tokenHasRefreshToken: Boolean(oAuth2Client.credentials.refresh_token),
          expiryDate: oAuth2Client.credentials.expiry_date || null
        }, null, 2)
      }]
    };
  }

  if (name === "list_files") {
    let q = args.query || "";
    if (q && !q.includes("contains") && !q.includes("=") && !q.includes("'")) {
      q = `name contains '${q.replaceAll("'", "\\'")}'`;
    }
    const res = await drive.files.list({
      q: q || undefined,
      fields: "files(id,name,mimeType,modifiedTime)",
      pageSize: 20
    });
    return { content: [{ type: "text", text: JSON.stringify(res.data.files, null, 2) }] };
  }

  if (name === "read_sheet") {
    const meta = await sheets.spreadsheets.get({ spreadsheetId: args.fileId });
    const sheetNames = meta.data.sheets.map((s) => s.properties.title);
    let output = "";
    for (const sheetName of sheetNames) {
      const res = await sheets.spreadsheets.values.get({
        spreadsheetId: args.fileId,
        range: sheetName
      });
      const rows = res.data.values || [];
      output += `\n=== Sheet: ${sheetName} ===\n`;
      output += rows.map((row) => row.join("\t")).join("\n");
      output += "\n";
    }
    return { content: [{ type: "text", text: output }] };
  }

  if (name === "read_sheet_range") {
    const res = await sheets.spreadsheets.values.get({
      spreadsheetId: args.fileId,
      range: args.range
    });
    const rows = res.data.values || [];
    return { content: [{ type: "text", text: rows.map((row) => row.join("\t")).join("\n") }] };
  }

  if (name === "read_sheet_formula_range") {
    const res = await sheets.spreadsheets.values.get({
      spreadsheetId: args.fileId,
      range: args.range,
      valueRenderOption: "FORMULA"
    });
    const rows = res.data.values || [];
    return { content: [{ type: "text", text: rows.map((row) => row.join("\t")).join("\n") }] };
  }

  if (name === "write_sheet") {
    if (args.append) {
      await sheets.spreadsheets.values.append({
        spreadsheetId: args.fileId,
        range: args.range,
        valueInputOption: "USER_ENTERED",
        requestBody: { values: args.values }
      });
    } else {
      await sheets.spreadsheets.values.update({
        spreadsheetId: args.fileId,
        range: args.range,
        valueInputOption: "USER_ENTERED",
        requestBody: { values: args.values }
      });
    }
    return { content: [{ type: "text", text: `Successfully written to ${args.range}` }] };
  }

  if (name === "duplicate_sheet") {
    const meta = await sheets.spreadsheets.get({ spreadsheetId: args.fileId });
    const sheetList = meta.data.sheets || [];
    const sourceSheet = sheetList.find((s) => s.properties.title === args.sourceSheetName)
      || sheetList.find((s) => s.properties.title.toLowerCase() === args.sourceSheetName.toLowerCase());
    const existingTarget = sheetList.find((s) => s.properties.title === args.targetSheetName)
      || sheetList.find((s) => s.properties.title.toLowerCase() === args.targetSheetName.toLowerCase());

    if (!sourceSheet) {
      throw new Error(`Source sheet not found: ${args.sourceSheetName}`);
    }

    if (existingTarget) {
      return { content: [{ type: "text", text: `Sheet already exists: ${existingTarget.properties.title}` }] };
    }

    const insertSheetIndex = typeof sourceSheet.properties.index === "number"
      ? sourceSheet.properties.index + 1
      : undefined;

    const res = await sheets.spreadsheets.batchUpdate({
      spreadsheetId: args.fileId,
      requestBody: {
        requests: [{
          duplicateSheet: {
            sourceSheetId: sourceSheet.properties.sheetId,
            insertSheetIndex,
            newSheetName: args.targetSheetName
          }
        }]
      }
    });

    const duplicated = res.data.replies?.[0]?.duplicateSheet?.properties;
    return {
      content: [{
        type: "text",
        text: JSON.stringify({
          id: duplicated?.sheetId,
          title: duplicated?.title || args.targetSheetName
        }, null, 2)
      }]
    };
  }

  if (name === "upload_file") {
    const fileStream = createReadStream(args.localPath);
    const res = await drive.files.create({
      requestBody: {
        name: args.fileName,
        parents: args.folderId ? [args.folderId] : undefined
      },
      media: {
        mimeType: args.mimeType || "application/octet-stream",
        body: fileStream
      },
      fields: "id,name,webViewLink"
    });

    await drive.permissions.create({
      fileId: res.data.id,
      requestBody: { role: "reader", type: "anyone" }
    });
    return {
      content: [{
        type: "text",
        text: JSON.stringify({ id: res.data.id, name: res.data.name, link: res.data.webViewLink })
      }]
    };
  }

  if (name === "get_folder_id") {
    const safeFolderName = args.folderName.replaceAll("'", "\\'");
    const res = await drive.files.list({
      q: `name contains '${safeFolderName}' and mimeType = 'application/vnd.google-apps.folder'`,
      fields: "files(id,name)",
      pageSize: 5
    });
    return { content: [{ type: "text", text: JSON.stringify(res.data.files, null, 2) }] };
  }

  throw new Error(`Unknown tool: ${name}`);
}

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  try {
    return await handleTool(req);
  } catch (error) {
    return {
      isError: true,
      content: [{ type: "text", text: formatError(error) }]
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
