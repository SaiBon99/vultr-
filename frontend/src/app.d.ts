// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
  namespace App {
    // interface Error {}
    // interface Locals {}
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }
}

// JSON fixtures from ../contracts, resolved by the Vite alias in vite.config.ts.
declare module "$contracts/*" {
  const value: unknown;
  export default value;
}

export {};
