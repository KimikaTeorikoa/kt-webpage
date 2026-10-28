document.addEventListener("DOMContentLoaded", function () {
  const profileViews = document.querySelector("[data-profile-views]");
  if (profileViews) {
    const panels = Array.from(profileViews.querySelectorAll("[data-profile-view-panel]"));
    const links = Array.from(document.querySelectorAll("[data-profile-view-link]"));
    const availableViews = new Set(panels.map((panel) => panel.dataset.profileViewPanel));

    const showProfileView = (view, updateHistory = false) => {
      const activeView = availableViews.has(view) ? view : "latest-publications";
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.profileViewPanel !== activeView;
      });
      links.forEach((link) => {
        if (link.dataset.profileViewLink === activeView) {
          link.setAttribute("aria-current", "page");
        } else {
          link.removeAttribute("aria-current");
        }
      });
      document.querySelector(".member-profile-nav__dropdown[open]")?.removeAttribute("open");

      if (updateHistory) {
        window.history.pushState(null, "", `${window.location.pathname}${window.location.search}#${activeView}`);
      }
    };

    links.forEach((link) => {
      link.addEventListener("click", (event) => {
        const view = link.dataset.profileViewLink;
        if (!availableViews.has(view)) return;
        event.preventDefault();
        showProfileView(view, true);
      });
    });

    const showViewFromLocation = () => {
      showProfileView(window.location.hash.slice(1));
    };

    window.addEventListener("hashchange", showViewFromLocation);
    window.addEventListener("popstate", showViewFromLocation);
    showViewFromLocation();
  }

  const carousel = document.querySelector(".landing-news");
  if (carousel) {
    const slides = Array.from(carousel.querySelectorAll(".landing-news__slide"));
    const previous = carousel.querySelector(".landing-news__control--previous");
    const next = carousel.querySelector(".landing-news__control--next");
    const toggle = carousel.querySelector(".landing-news__control--toggle");
    const moreLink = carousel.querySelector("[data-news-more]");
    const moreLabel = carousel.querySelector("[data-news-more-label]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let current = slides.findIndex((slide) => !slide.hidden);
    let userPaused = reducedMotion;
    let interacting = false;
    let timer;

    const showSlide = (index) => {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => {
        slide.hidden = slideIndex !== current;
      });
      if (moreLink) {
        moreLink.href = slides[current].dataset.moreUrl;
        if (moreLabel) {
          moreLabel.textContent = slides[current].dataset.moreLabel;
        }
      }
    };

    const updateTimer = () => {
      window.clearInterval(timer);
      if (!userPaused && !interacting && !document.hidden && slides.length > 1) {
        timer = window.setInterval(() => showSlide(current + 1), 3000);
      }
      if (toggle) {
        toggle.setAttribute("aria-pressed", userPaused ? "true" : "false");
        toggle.setAttribute("aria-label", userPaused ? "Resume news rotation" : "Pause news rotation");
        toggle.textContent = userPaused ? "Play" : "Pause";
      }
    };

    previous?.addEventListener("click", () => {
      showSlide(current - 1);
      updateTimer();
    });
    next?.addEventListener("click", () => {
      showSlide(current + 1);
      updateTimer();
    });
    toggle?.addEventListener("click", () => {
      userPaused = !userPaused;
      updateTimer();
    });
    carousel.addEventListener("mouseenter", () => {
      interacting = true;
      updateTimer();
    });
    carousel.addEventListener("mouseleave", () => {
      interacting = false;
      updateTimer();
    });
    carousel.addEventListener("focusin", () => {
      interacting = true;
      updateTimer();
    });
    carousel.addEventListener("focusout", (event) => {
      if (!carousel.contains(event.relatedTarget)) {
        interacting = false;
        updateTimer();
      }
    });
    document.addEventListener("visibilitychange", updateTimer);
    updateTimer();
  }

  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".site-nav");

  if (!toggle || !nav) {
    return;
  }

  toggle.addEventListener("click", function () {
    const isOpen = nav.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });
});
