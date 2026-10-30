"use strict";

let conviteInstalacao;
window.addEventListener("beforeinstallprompt", event => {
  event.preventDefault();
  conviteInstalacao = event;
});
window.mostrarInstalacao = async () => {
  if (window.matchMedia("(display-mode: standalone)").matches || navigator.standalone) {
    aviso("O DevMaster já está aberto como aplicativo.");
    return;
  }
  if (conviteInstalacao) {
    await conviteInstalacao.prompt();
    conviteInstalacao = null;
    return;
  }
  janela("Instalar DevMaster", h("div", {},
    h("p", {}, "No iPhone ou iPad, abra este endereço no Safari, toque em Compartilhar e escolha Adicionar à Tela de Início. Confirme em Adicionar."),
    h("p", {}, "Em outros dispositivos, use Instalar aplicativo no menu do navegador. O painel precisa de internet para consultar e salvar dados.")),
    fechar => [h("button", { class: "btn", onclick: fechar }, "Entendi")]);
};

// Atualiza o worker na próxima abertura, sem recarregar formulários em edição.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

// VisualViewport acompanha o teclado do iOS para manter ações e diálogos acessíveis.
function atualizarViewport() {
  const viewport = window.visualViewport;
  const teclado = viewport ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
  document.documentElement.style.setProperty("--teclado", `${teclado > 100 ? teclado : 0}px`);
  document.documentElement.style.setProperty("--altura-visivel", `${viewport?.height || window.innerHeight}px`);
}
window.visualViewport?.addEventListener("resize", atualizarViewport);
window.visualViewport?.addEventListener("scroll", atualizarViewport);
window.addEventListener("resize", atualizarViewport);
atualizarViewport();
