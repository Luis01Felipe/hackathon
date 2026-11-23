// Teste de ponta a ponta: sair do passo 6 e voltar logo, com o IFC ainda convertendo.
// O visualizador 3D precisa ser descartado sem erros não tratados, e a volta precisa
// mostrar o modelo.
//
// Pré-requisitos: frontend compilado (npm run build) e backend no ar
// (cd backend; uv run editalcheck servidor).
//
// Uso: node scripts/e2e-ida-e-volta.mjs [url] (padrão: http://127.0.0.1:8000)
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const URL_APP = process.argv[2] ?? "http://127.0.0.1:8000";
/** Espera antes de cada ida e volta: cobre a conversão do IFC e a carga no worker. */
const ATRASOS_MS = [100, 300, 500, 700, 900, 1100, 1300, 1500];
const LIMITE_FLUXO_MS = 180_000;
const LIMITE_MODELO_MS = 240_000;

const BOTOES_AVANCO = [
  /^Confirmar e gerar RI/,
  /^Usar dados de exemplo/,
  /^Continuar para os tópicos →$/,
  /^Conferir no edital e gerar RI \(\d+\) →$/,
  /^Gerar requisitos \(RI\)$/,
  /^Gerar IDS →$/,
  /^Executar verificação →$/,
  /^Gerar IDS$/,
  /^Iniciar verificação$/,
  /^Abrir resultados →$/,
  /^Ver resultados →$/,
];

/** Botões que continuam na tela depois do clique: clica uma vez só. */
const BOTOES_UMA_VEZ = [/^Aceitar todos os verificáveis$/];

const erros = [];
const clicados = new Set();

function registrar(origem, texto) {
  erros.push(`[${origem}] ${texto}`);
}

async function passoAtual(page) {
  const texto = await page.locator(".stepper li.ativo .passo-texto strong").textContent();
  return texto?.trim() ?? "";
}

/** Clica no primeiro botão de avanço visível e habilitado. */
async function avancar(page) {
  const pendentes = BOTOES_UMA_VEZ.filter((rotulo) => !clicados.has(rotulo.source));
  for (const rotulo of [...pendentes, ...BOTOES_AVANCO]) {
    const botao = page.getByRole("button", { name: rotulo });
    if ((await botao.count()) === 0) continue;
    const primeiro = botao.first();
    if (!(await primeiro.isVisible()) || !(await primeiro.isEnabled())) continue;
    await primeiro.click();
    clicados.add(rotulo.source);
    return true;
  }
  return false;
}

async function chegarAosResultados(page) {
  const limite = Date.now() + LIMITE_FLUXO_MS;
  while (Date.now() < limite) {
    if ((await passoAtual(page)) === "Resultados") return;
    await avancar(page);
    await page.waitForTimeout(500);
  }
  throw new Error("O fluxo da demo não chegou ao passo 6 (Resultados).");
}

async function clicarPasso(page, numero) {
  await page.locator(".stepper li").nth(numero - 1).locator("button").click();
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on("pageerror", (e) => registrar("pageerror", e.stack ?? String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") registrar("console", m.text());
  });
  // Cada visualizador tem um worker de fragments; os descartados precisam ser encerrados.
  let workersVivos = 0;
  page.on("worker", (worker) => {
    if (!worker.url().includes("/fragments/")) return;
    workersVivos += 1;
    worker.on("close", () => {
      workersVivos -= 1;
    });
  });

  try {
    await page.goto(URL_APP);
    await chegarAosResultados(page);

    for (const atraso of ATRASOS_MS) {
      await page.waitForTimeout(atraso);
      await clicarPasso(page, 5);
      await page.waitForTimeout(300);
      await clicarPasso(page, 6);
    }

    await page.locator(".viewer-canvas canvas").first().waitFor({ timeout: LIMITE_MODELO_MS });
    await page.waitForFunction(() => !document.querySelector(".viewer-overlay"), null, { timeout: LIMITE_MODELO_MS });
    // Dá tempo para mensagens atrasadas dos workers descartados chegarem.
    await page.waitForTimeout(3000);
    if (await page.locator(".viewer-falha").count()) registrar("tela", "O visualizador caiu no plano B.");
    if (workersVivos > 1) registrar("workers", `${workersVivos} workers de fragments vivos; o esperado é 1.`);
  } catch (e) {
    registrar("roteiro", e instanceof Error ? e.message : String(e));
  } finally {
    await browser.close();
  }

  if (erros.length) {
    console.error(`FALHOU: ${erros.length} erro(s).`);
    for (const erro of erros) console.error(erro);
    process.exitCode = 1;
    return;
  }
  console.log(`OK: ${ATRASOS_MS.length} idas e voltas ao passo 6 sem erros; o modelo 3D apareceu.`);
}

await main();
