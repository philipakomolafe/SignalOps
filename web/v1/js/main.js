const revealElements = Array.from(document.querySelectorAll('.reveal'));

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('show');
      observer.unobserve(entry.target);
    }
  });
}, {
  threshold: 0.18
});

revealElements.forEach((el, index) => {
  el.style.animationDelay = `${index * 70}ms`;
  observer.observe(el);
});

const year = document.getElementById('year');
if (year) {
  year.textContent = String(new Date().getFullYear());
}
