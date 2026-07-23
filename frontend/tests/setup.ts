import "@testing-library/jest-dom/vitest";

// jsdom does not implement ResizeObserver. Carbon uses it for modal and menu
// layout in current releases, so provide the inert browser-test equivalent.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverStub;
}

// Node 25 exposes an incomplete experimental `localStorage` unless it is
// launched with a backing file. Give jsdom tests a deterministic in-memory
// implementation so persisted Zustand stores behave the same on every Node
// version and in CI.
const memory = new Map<string, string>();
const localStorageStub: Storage = {
  get length() {
    return memory.size;
  },
  clear() {
    memory.clear();
  },
  getItem(key) {
    return memory.get(key) ?? null;
  },
  key(index) {
    return Array.from(memory.keys())[index] ?? null;
  },
  removeItem(key) {
    memory.delete(key);
  },
  setItem(key, value) {
    memory.set(key, String(value));
  },
};

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: localStorageStub,
});
