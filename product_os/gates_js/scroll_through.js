async () => {
  for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight / 2) {
    scrollTo(0, y); await new Promise(done => setTimeout(done, 60));
  }
  scrollTo(0, 0);
}