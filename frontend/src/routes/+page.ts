import { getApi } from "#lib/api/index.js";
import type { PageLoad } from "./$types";

export const load: PageLoad = async () => ({
  list: await getApi().listQuarantine(),
});
