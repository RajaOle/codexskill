import { spawn } from "node:child_process";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

const SCRIPT = "/home/olekamole/scripts/moura_campaign_claims.py";

const submitParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    requester_phone: {
      type: "string",
      description: "Verified platform sender phone for the winner. Must match the listed winner WhatsApp phone in the current campaign Google Doc."
    },
    chat_kind: {
      type: "string",
      enum: ["direct", "group"],
      description: "Current chat kind. Claim submission is allowed only when this is direct."
    },
    source_chat_id: {
      type: "string",
      description: "Current WhatsApp chat id or phone, for audit only. Use the verified direct chat phone when available."
    },
    campaign_id: {
      type: "string",
      description: "Current campaign id from the current campaign Google Doc."
    },
    winner_rank: {
      type: "integer",
      enum: [1, 2, 3],
      description: "Winner rank being claimed."
    },
    instagram_username: {
      type: "string",
      description: "Instagram username used for the giveaway, without needing @. Used only for matching when available."
    },
    bank_name: {
      type: "string",
      description: "Bank name for the cash prize payout."
    },
    account_holder_name: {
      type: "string",
      description: "Bank account holder name for the cash prize payout."
    },
    account_number: {
      type: "string",
      description: "Bank account number for the cash prize payout. Never repeat this value back in chat."
    }
  },
  required: [
    "requester_phone",
    "chat_kind",
    "source_chat_id",
    "campaign_id",
    "winner_rank",
    "bank_name",
    "account_holder_name",
    "account_number"
  ]
};

const contactParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    requester_phone: {
      type: "string",
      description: "Verified platform sender phone for the winner/contact."
    },
    chat_kind: {
      type: "string",
      enum: ["direct", "group"],
      description: "Current chat kind."
    },
    source_chat_id: {
      type: "string",
      description: "Current WhatsApp chat id or phone, for audit only."
    },
    campaign_id: {
      type: "string",
      description: "Current campaign id from the current campaign Google Doc."
    },
    winner_rank: {
      type: "integer",
      description: "Winner rank if known. Omit or use 0 if not known yet."
    },
    instagram_username: {
      type: "string",
      description: "Instagram username mentioned by the user, without needing @."
    },
    stage: {
      type: "string",
      enum: [
        "claimed_winner",
        "verified_story",
        "payout_requested",
        "claim_submitted",
        "voucher_delivered",
        "admin_verify_needed"
      ],
      description: "Non-sensitive contact stage."
    },
    note: {
      type: "string",
      description: "Short non-sensitive note. Never include account numbers, OTPs, passwords, IDs, or full private details."
    }
  },
  required: ["requester_phone", "chat_kind", "source_chat_id", "campaign_id", "stage"]
};

const statusParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    requester_phone: {
      type: "string",
      description: "Verified platform sender phone for Ibnu or Apin."
    },
    campaign_id: {
      type: "string",
      description: "Current campaign id from the current campaign Google Doc."
    }
  },
  required: ["requester_phone"]
};

function runCampaignCommand(command, params) {
  return new Promise((resolve, reject) => {
    const payload = Buffer.from(JSON.stringify(params), "utf8").toString("base64");
    const child = spawn("/usr/bin/python3", [SCRIPT, command, "--payload-b64", payload], {
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("moura campaign claim submission timed out"));
    }, 45000);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0) {
        reject(new Error(stderr.trim() || stdout.trim() || `moura campaign claim submission failed with code ${code}`));
        return;
      }
      resolve(stdout.trim());
    });
  });
}

export default defineToolPlugin({
  id: "moura-campaign-claims",
  name: "Moura Campaign Claims",
  description: "Secure campaign winner contact and cash-prize claim handling for Moura Alexandra.",
  tools: (tool) => [
    tool({
      name: "moura_campaign_current",
      description: "Read the current Mouru campaign source of truth from the approved Google Doc. Use for campaign status, rules, winners, claim state, voucher codes, links, and campaign-specific reply text.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {}
      },
      execute: async () => {
        const output = await runCampaignCommand("current-json", {});
        return JSON.parse(output);
      }
    }),
    tool({
      name: "moura_campaign_claim_submit",
      description: "Submit one verified Mouru campaign cash-prize claim from a listed winner in DM only. Stores payout details locally and notifies directors with a masked claim reference.",
      parameters: submitParameters,
      execute: async (params) => {
        const output = await runCampaignCommand("submit-json", params);
        return JSON.parse(output);
      }
    }),
    tool({
      name: "moura_campaign_contact_record",
      description: "Record a non-sensitive campaign winner contact from WhatsApp so verified directors can later ask who has contacted Moura. Never store account numbers, OTPs, passwords, IDs, or full private payout data here.",
      parameters: contactParameters,
      execute: async (params) => {
        const output = await runCampaignCommand("contact-json", params);
        return JSON.parse(output);
      }
    }),
    tool({
      name: "moura_campaign_claim_status",
      description: "Return a non-sensitive campaign contact and claim summary for verified Ibnu or Apin only. Masks phones and account numbers.",
      parameters: statusParameters,
      execute: async (params) => {
        const output = await runCampaignCommand("status-json", params);
        return JSON.parse(output);
      }
    })
  ]
});
