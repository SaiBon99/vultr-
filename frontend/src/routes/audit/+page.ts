import { getApi } from "#lib/api/index.js";
import { verifyAuditChain } from "#lib/crypto/auditChain.js";
import type { PageLoad } from "./$types";

export const load: PageLoad = async () => {
  const log = await getApi().getAudit();
  // The server reports chain_valid; recompute it locally so the UI never trusts it blindly.
  const local = await verifyAuditChain(log.events);
  return { log, local };
};
