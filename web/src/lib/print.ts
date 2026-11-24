const DARK = "th-dark";
const LIGHT = "th-light";
const PRINTING = "codes";

export function printInLight(): void {
  const root = document.documentElement;
  const hadDark = root.classList.contains(DARK);
  const hadLight = root.classList.contains(LIGHT);
  root.classList.remove(DARK);
  root.classList.add(LIGHT);
  root.dataset.printing = PRINTING;
  const restore = () => {
    delete root.dataset.printing;
    if (!hadLight) {
      root.classList.remove(LIGHT);
    }
    if (hadDark) {
      root.classList.add(DARK);
    }
  };
  window.addEventListener("afterprint", restore, { once: true });
  window.print();
}
