import { ApiError, describeError, getApi } from "#lib/api/index.js";
import type { PageLoad } from "./$types";

/** Initial review queue; errors render inline so a missing token does not hit the error page. */
export const load: PageLoad = async () => {
  try {
    return {
      list: await getApi().listQuarantine("quarantined"),
      error: null,
      status: 200,
    };
  } catch (err) {
    return {
      list: null,
      error: describeError(err, "Could not load the quarantine queue."),
      status: err instanceof ApiError ? err.status : 0,
    };
  }
};
