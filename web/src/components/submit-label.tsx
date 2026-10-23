const LAYER = "col-start-1 row-start-1";

function layerClass(visible: boolean): string {
  if (visible) {
    return LAYER;
  }
  return `${LAYER} invisible`;
}

export function SubmitLabel({ idle, busy, pending }: { idle: string; busy: string; pending: boolean }) {
  return (
    <span className="grid justify-items-center whitespace-nowrap" data-submit-label>
      <span aria-hidden={pending} className={layerClass(!pending)}>
        {idle}
      </span>
      <span aria-hidden={!pending} className={layerClass(pending)}>
        {busy}
      </span>
    </span>
  );
}
