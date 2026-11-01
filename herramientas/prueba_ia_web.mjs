// Prueba la IA de la versión web con el modelo real, en Chromium (CI):
//   1. "Solo el audio": la IA escribe la letra de Sound of You → % de palabras
//      acertadas contra la letra de ejemplos/canciones.txt.
//   2. "Con su letra": la IA sincroniza Ghost of you → diferencia de los
//      inicios de línea contra ejemplos/tiempos.json (calculados en Python).
// Uso: python web/servir.py --sin-navegador & node herramientas/prueba_ia_web.mjs
import { readFileSync } from "fs";
import { chromium } from "playwright";

const RAIZ = new URL("..", import.meta.url).pathname;
const URL_WEB = process.env.URL_WEB || "http://localhost:8000";
const MODELO = process.env.MODELO_IA || "rapido";

const normalizar = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/['’]/g, "").replace(/[^a-z0-9ñ ]+/g, " ").split(/\s+/).filter(Boolean);
function acierto(referencia, escrito) {           // palabras en común en orden (LCS) / palabras de la letra
  const a = normalizar(referencia), b = normalizar(escrito);
  const fila = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    let diagonal = 0;
    for (let j = 1; j <= b.length; j++) {
      const arriba = fila[j];
      fila[j] = a[i - 1] === b[j - 1] ? diagonal + 1 : Math.max(fila[j], fila[j - 1]);
      diagonal = arriba;
    }
  }
  return fila[b.length] / a.length;
}
function letraDe(nombre) {
  const texto = readFileSync(RAIZ + "ejemplos/canciones.txt", "utf8").split("\n").filter((l) => !l.startsWith("//"));
  const bloques = texto.join("\n").split(/\n\s*\n/).map((b) => b.trim().split("\n"));
  return bloques.find((b) => b[0].trim() === nombre).slice(1).filter((l) => !/^(chorus|coro)\b/i.test(l.trim()));
}

const navegador = await chromium.launch();
const pagina = await navegador.newPage();
pagina.on("console", (m) => { if (m.type() === "error") console.log("consola:", m.text().slice(0, 300)); });
pagina.on("pageerror", (e) => console.log("error:", e.message));
let fallos = 0;

// 1. La IA escribe la letra
await pagina.goto(`${URL_WEB}/#agregar?forma=audio`);
await pagina.setInputFiles("#form-audio [name=audio]", RAIZ + "ejemplos/Sound_of_You.mp3");
await pagina.fill("#form-audio [name=nombre]", "Sound prueba IA");   // "Sound of You" ya existe
await pagina.selectOption("#form-audio [name=idioma]", "en");
await pagina.selectOption("#form-audio [name=modelo]", MODELO);
let inicio = Date.now();
await pagina.click("#form-audio [type=submit]");
const avance = setInterval(async () => console.log("  ", await pagina.textContent("#avance-ia p").catch(() => "")), 20000);
try {
  await pagina.waitForSelector("#form-revision", { timeout: 25 * 60 * 1000 });
  const escrita = await pagina.inputValue("#form-revision textarea");
  const dep = await pagina.evaluate(() => globalThis.__iaDepuracion);
  for (const v of dep?.ventanas || []) console.log(`  ventana ${v.desde}s: ${JSON.stringify(v.texto).slice(0, 160)} · ${JSON.stringify(v.palabras)}`);
  const porcentaje = acierto(letraDe("Sound of You").join(" "), escrita) * 100;
  console.log(`\n1. Letra escrita por la IA (${MODELO}) en ${Math.round((Date.now() - inicio) / 1000)} s: ${porcentaje.toFixed(1)} % de las palabras\n`);
  console.log(escrita);
  if (porcentaje < 60) { console.log("Acierto demasiado bajo"); fallos++; }
  await pagina.click("#form-revision [type=submit]");
  await pagina.waitForSelector(".estado-sincronia");
} catch (error) {
  console.log("1. FALLÓ:", error.message, "·", await pagina.textContent("#aviso"));
  fallos++;
}
clearInterval(avance);

// 2. La IA sincroniza una letra escrita
await pagina.goto(`${URL_WEB}/#agregar`);
const ghost = letraDe("Ghost of you");
await pagina.fill("#form-cancion [name=nombre]", "Ghost prueba IA");
await pagina.fill("#form-cancion [name=letra]", ghost.join("\n"));
await pagina.setInputFiles("#form-cancion [name=audio]", RAIZ + "ejemplos/Ghost_of_you_Remastered.mp3");
inicio = Date.now();
await pagina.click("#form-cancion [type=submit]");
try {
  await pagina.waitForFunction(() => document.querySelector(".estado-sincronia")?.textContent.includes("sincronizada"), null, { timeout: 25 * 60 * 1000, polling: 2000 });
  const dep2 = await pagina.evaluate(() => globalThis.__iaDepuracion);
  for (const v of dep2?.ventanas || []) console.log(`  ventana ${v.desde}s: ${JSON.stringify(v.texto).slice(0, 160)} · ${JSON.stringify(v.palabras)}`);
  const extras = await pagina.evaluate(() => JSON.parse(localStorage.getItem("karaoke:extras")));
  const propia = Object.entries(extras).find(([, x]) => x.sincronizada === "ia" && x.tiempos?.length === 19);
  const esperados = JSON.parse(readFileSync(RAIZ + "ejemplos/tiempos.json", "utf8"))["Ghost of you"].tiempos;
  const difs = propia[1].tiempos.map((t, i) => Math.abs(t - esperados[i]));
  const media = difs.reduce((a, b) => a + b, 0) / difs.length;
  console.log(`\n2. Sincronía de Ghost of you en ${Math.round((Date.now() - inicio) / 1000)} s: diferencia media ${media.toFixed(2)} s con Python (máxima ${Math.max(...difs).toFixed(2)} s)`);
  console.log("   web:   ", propia[1].tiempos.join(" "));
  console.log("   python:", esperados.join(" "));
  if (media > 1.5) { console.log("Diferencia demasiado grande"); fallos++; }
} catch (error) {
  console.log("2. FALLÓ:", error.message, "·", await pagina.textContent("#aviso").catch(() => ""));
  fallos++;
}
await navegador.close();
process.exit(fallos ? 1 : 0);
