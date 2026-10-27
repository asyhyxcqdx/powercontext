(function () {
  "use strict";

  const triggers = Array.from(document.querySelectorAll(".shot-btn"));
  if (!triggers.length) return;

  const lightbox = document.getElementById("lightbox");
  const image = document.getElementById("lb-image");
  const title = document.getElementById("lb-title");
  const caption = document.getElementById("lb-caption");
  const counter = document.getElementById("lb-count");
  const closeBtn = lightbox.querySelector(".lb-close");
  const prevBtn = lightbox.querySelector(".lb-prev");
  const nextBtn = lightbox.querySelector(".lb-next");

  let current = 0;
  let lastTrigger = null;

  function render(index) {
    current = (index + triggers.length) % triggers.length;
    const trigger = triggers[current];
    const thumb = trigger.querySelector("img");
    image.src = trigger.dataset.full;
    image.alt = thumb ? thumb.alt : trigger.dataset.title || "截图";
    title.textContent = trigger.dataset.title || "";
    caption.textContent = trigger.dataset.caption || "";
    counter.textContent = `${current + 1} / ${triggers.length}`;
    lightbox.setAttribute("aria-label", `截图预览：${trigger.dataset.title || ""}`);
  }

  function open(index, trigger) {
    lastTrigger = trigger || null;
    render(index);
    lightbox.hidden = false;
    document.body.style.overflow = "hidden";
    closeBtn.focus();
  }

  function close() {
    lightbox.hidden = true;
    document.body.style.overflow = "";
    if (lastTrigger) lastTrigger.focus();
  }

  triggers.forEach((trigger, index) => {
    trigger.addEventListener("click", () => open(index, trigger));
  });

  closeBtn.addEventListener("click", close);
  prevBtn.addEventListener("click", () => render(current - 1));
  nextBtn.addEventListener("click", () => render(current + 1));

  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) close();
  });

  document.addEventListener("keydown", (event) => {
    if (lightbox.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      render(current - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      render(current + 1);
    } else if (event.key === "Tab") {
      const focusables = [closeBtn, prevBtn, nextBtn];
      const active = document.activeElement;
      const at = focusables.indexOf(active);
      event.preventDefault();
      const next = event.shiftKey
        ? focusables[(at <= 0 ? focusables.length : at) - 1]
        : focusables[(at + 1) % focusables.length];
      next.focus();
    }
  });
})();
