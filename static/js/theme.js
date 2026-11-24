(function(){var t;try{t=localStorage.getItem("km-theme")}catch(e){}
document.documentElement.dataset.theme=t||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light")})();
