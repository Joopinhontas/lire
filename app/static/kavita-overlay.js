(() => {
  const button = document.getElementById("lire-back");
  if (!button) return;
  const readerRoute = /\/(manga|book|pdf|reader)\//;
  let last = "";
  const sync = () => {
    if (location.pathname === last) return;
    last = location.pathname;
    button.dataset.hidden = readerRoute.test(last) ? "true" : "false";
  };
  sync();
  setInterval(sync, 500);
})();
