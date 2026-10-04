"""Vista HTML autocontenida del plan semanal: hoy, semana, rutinas, menú y lista de la compra.

Se genera junto al plan (datos/<perfil>/planes/plan_<semana>.html) y funciona sin conexión,
también en el móvil (por ejemplo, abriéndola desde la app de OneDrive).
Las casillas marcadas (series hechas, compra) se guardan en el navegador (localStorage).
"""
from __future__ import annotations

import json
from pathlib import Path

FASES = {"reintroduccion": "Reintroducción", "acumulacion": "Acumulación", "intensificacion": "Intensificación",
         "descarga": "Descarga", "mantenimiento": "Mantenimiento"}


def generar(plan: dict, paquete: dict, carpeta: Path | str) -> Path:
    datos = {
        "plan": plan,
        "semana": paquete["semana"],
        "fase": FASES.get(paquete["semana"]["fase"], paquete["semana"]["fase"]),
        "nutricion": paquete["objetivos"]["nutricion"],
        "zonas": paquete["estado"].get("cardio_referencia", {}).get("zonas_fc", {}),
        "evitar_usuario": paquete["perfil"].get("preferencias_alimentarias", {}).get("no_le_gusta", []),
    }
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    html = PLANTILLA.replace("__DATOS__", js).replace("__TITULO__", f"Plan {paquete['semana']['inicio']}")
    destino = Path(carpeta) / "planes" / f"plan_{plan['semana_inicio']}.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino


PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<style>
:root{--bg:#f6f5f2;--panel:#fff;--ink:#1d1f22;--muted:#6b6f76;--line:#e4e2dc;--accent:#1f6f5c;--accent-soft:#e3f0ec;
--warn:#9a5b00;--warn-soft:#fbf0de;--chip:#efeee9;--fuerza:#1f6f5c;--cardio:#2f5f9e;--done:#9aa09d}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--panel:#1c1e21;--ink:#ebeae6;--muted:#9a9ea4;--line:#2c2f33;
--accent:#5fc2a6;--accent-soft:#1d332d;--warn:#f0b35a;--warn-soft:#3a2c17;--chip:#26292d;--fuerza:#5fc2a6;--cardio:#7fa8e0;--done:#5b605d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:980px;margin:auto}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);font-size:14px}
.enfoque{margin:10px 0 0;font-size:14px}
.avisos{margin:10px 0 0;padding:10px 12px;list-style:disc;background:var(--warn-soft);color:var(--warn);border-radius:10px;font-size:13.5px}
.avisos li{margin:2px 0 2px 18px}
nav{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
nav div{display:flex;gap:4px;max-width:980px;margin:auto;padding:8px 12px;overflow-x:auto}
nav button{border:0;background:none;color:var(--muted);padding:8px 12px;border-radius:999px;font:inherit;font-weight:600;cursor:pointer;white-space:nowrap}
nav button.on{background:var(--accent-soft);color:var(--accent)}
main{max-width:980px;margin:auto;padding:12px 16px 60px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:0 0 12px}
.card h3{margin:0 0 8px;font-size:16px}
.dias{display:flex;gap:6px;margin:0 0 12px;overflow-x:auto}
.dias button{flex:1;min-width:44px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:10px;padding:6px 4px;font:inherit;cursor:pointer}
.dias button small{display:block;color:var(--muted);font-size:11px}
.dias button.on{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.tag{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--muted);margin-right:6px}
.tag.fuerza{background:var(--accent-soft);color:var(--fuerza)} .tag.cardio{background:color-mix(in srgb,var(--cardio) 15%,transparent);color:var(--cardio)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px}
td.num{white-space:nowrap}
tr.hecho td{color:var(--done);text-decoration:line-through}
input[type=checkbox]{width:18px;height:18px;accent-color:var(--accent)}
.ej{margin:0 0 14px}
.ej h4{margin:0 0 4px;font-size:15px}
.ej .meta{color:var(--muted);font-size:12.5px;margin-bottom:4px}
.bloque{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--line);font-size:14px}
.bloque:last-child{border:0}
.grid7{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.grid7 .card{margin:0}
.kcal{display:flex;gap:14px;flex-wrap:wrap;font-size:13.5px;color:var(--muted);margin-top:6px}
.kcal b{color:var(--ink)}
.barra{height:6px;background:var(--chip);border-radius:6px;overflow:hidden;margin-top:6px}
.barra i{display:block;height:100%;background:var(--accent)}
.comida{padding:8px 0;border-bottom:1px solid var(--line)}
.comida:last-child{border:0}
.comida .h{display:flex;justify-content:space-between;font-weight:600}
.comida .h span{color:var(--muted);font-weight:500;font-size:13px}
.comida ul{margin:4px 0 0;padding-left:18px}
details{margin-top:4px} summary{cursor:pointer;color:var(--accent);font-size:13.5px}
.receta ol{padding-left:18px;margin:6px 0} .receta ul{padding-left:18px;margin:6px 0}
.sec h3{margin-bottom:4px}
.compra li{list-style:none;display:flex;gap:10px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}
.compra ul{padding:0;margin:0}
.compra li.hecho span{color:var(--done);text-decoration:line-through}
.vacio{color:var(--muted);font-style:italic}
@media print{nav{display:none}body{background:#fff}}
</style>
</head>
<body>
<header>
  <h1 id="titulo"></h1>
  <div class="sub" id="sub"></div>
  <p class="enfoque" id="enfoque"></p>
  <ul class="avisos" id="avisos"></ul>
</header>
<nav><div id="tabs"></div></nav>
<main id="main"></main>
<script>
const D = __DATOS__;
const P = D.plan;
const DIAS_CORTOS = {lunes:"L",martes:"M",miercoles:"X",jueves:"J",viernes:"V",sabado:"S",domingo:"D"};
const NOMBRE_DIA = {lunes:"Lunes",martes:"Martes",miercoles:"Miércoles",jueves:"Jueves",viernes:"Viernes",sabado:"Sábado",domingo:"Domingo"};
const COMIDA = {desayuno:"Desayuno",media_manana:"Media mañana",almuerzo:"Almuerzo",merienda:"Merienda",cena:"Cena",pre_entreno:"Pre-entreno",post_entreno:"Post-entreno",recena:"Recena"};
const CARDIO = {cinta:"Cinta",carrera_exterior:"Carrera exterior",bici_indoor:"Bici indoor",remo:"Remo",eliptica:"Elíptica",hiit:"HIIT",movilidad:"Movilidad",caminar:"Caminar"};
const SERIE = {warmup:"Calent.",normal:"Trabajo",failure:"Al fallo",dropset:"Drop set"};
const SECCION = {fruta_verdura:"Fruta y verdura",carne:"Carne",pescado:"Pescado",huevos_lacteos:"Huevos y lácteos",panaderia:"Panadería",despensa:"Despensa",congelados:"Congelados",bebidas:"Bebidas",otros:"Otros"};
const recetas = Object.fromEntries(P.nutricion.recetas.map(r=>[r.id,r]));
const rutinas = Object.fromEntries(P.entrenamiento.rutinas.map(r=>[r.id,r]));
const K = "fitplan:"+P.semana_inicio+":";
const leer = k => { try { return JSON.parse(localStorage.getItem(K+k)||"null"); } catch(e){ return null; } };
const guardar = (k,v) => { try { localStorage.setItem(K+k, JSON.stringify(v)); } catch(e){} };
const esc = s => String(s??"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtFecha = f => { const d=new Date(f+"T12:00:00"); return d.toLocaleDateString("es-ES",{day:"numeric",month:"short"}); };
const r0 = x => Math.round(x||0);

// cabecera
const ini = P.entrenamiento.dias[0].fecha, fin = P.entrenamiento.dias[6].fecha;
document.getElementById("titulo").textContent = `Semana ${fmtFecha(ini)} – ${fmtFecha(fin)}`;
document.getElementById("sub").textContent = `Bloque ${D.semana.bloque} · semana ${D.semana.semana_en_bloque} · ${D.fase} · ${D.nutricion.kcal_entreno}/${D.nutricion.kcal_descanso} kcal · ${D.nutricion.proteina_g} g proteína`;
document.getElementById("enfoque").textContent = P.resumen.enfoque;
const av = document.getElementById("avisos");
(P.resumen.avisos||[]).forEach(a=>{ const li=document.createElement("li"); li.textContent=a; av.appendChild(li); });
if(!(P.resumen.avisos||[]).length) av.remove();

// día inicial: hoy si cae en la semana
const hoyISO = new Date().toISOString().slice(0,10);
let diaSel = P.entrenamiento.dias.findIndex(d=>d.fecha===hoyISO); if(diaSel<0) diaSel=0;

function htmlSesion(s, conCheck){
  if(s.tipo==="fuerza"){
    const r = rutinas[s.rutina_ref]; if(!r) return `<p class="vacio">Rutina ${esc(s.rutina_ref)} no encontrada</p>`;
    const hechas = leer("series")||{};
    let h = `<div class="card"><h3><span class="tag fuerza">Fuerza</span>${esc(r.titulo)}</h3><div class="sub">${esc(s.hora)} · ${s.duracion_min} min · ${esc(s.objetivo)}</div>`;
    if(r.notas) h += `<p class="sub">${esc(r.notas)}</p>`;
    r.ejercicios.forEach((e,ei)=>{
      h += `<div class="ej"><h4>${esc(e.nombre)}</h4><div class="meta">Descanso ${e.descanso_s}s${e.superset_id!=null?` · superserie ${e.superset_id}`:""}${e.notas?` · ${esc(e.notas)}`:""}</div><table><tr>${conCheck?"<th></th>":""}<th>Serie</th><th>Tipo</th><th>Peso</th><th>Reps</th><th>RPE</th></tr>`;
      e.series.forEach((x,si)=>{
        const id = `${s.rutina_ref}|${P.entrenamiento.dias[diaSel].fecha}|${ei}|${si}`;
        const ok = conCheck && hechas[id];
        const reps = x.reps_rango?`${x.reps_rango[0]}–${x.reps_rango[1]}`:(x.reps??(x.duracion_s?`${x.duracion_s}s`:"—"));
        h += `<tr class="${ok?"hecho":""}">${conCheck?`<td><input type="checkbox" data-serie="${id}" ${ok?"checked":""}></td>`:""}<td>${si+1}</td><td>${SERIE[x.tipo]||x.tipo}</td><td class="num">${x.peso_kg!=null?x.peso_kg+" kg":"PC"}</td><td class="num">${reps}</td><td>${x.rpe_objetivo??""}</td></tr>`;
      });
      h += `</table></div>`;
    });
    if(s.bloques_cardio) h += htmlBloques(s.bloques_cardio);
    return h+`</div>`;
  }
  return `<div class="card"><h3><span class="tag cardio">${CARDIO[s.tipo]||s.tipo}</span>${esc(s.objetivo)}</h3><div class="sub">${esc(s.hora)} · ${s.duracion_min} min</div>${htmlBloques(s.bloques_cardio||[])}${s.notas?`<p class="sub">${esc(s.notas)}</p>`:""}</div>`;
}
function htmlBloques(bs){
  return bs.map(b=>{
    const i=b.intensidad||{}; const z=i.zona?`${i.zona}${D.zonas[i.zona]?` (${D.zonas[i.zona][0]}–${D.zonas[i.zona][1]} ppm)`:""}`:"";
    const extra=[z, i.rpe?`RPE ${i.rpe}`:"", i.velocidad_kmh?`${i.velocidad_kmh} km/h`:"", i.inclinacion_pct!=null?`${i.inclinacion_pct}%`:"", i.ritmo_min_km?`${i.ritmo_min_km}/km`:"", i.vatios?`${i.vatios} W`:""].filter(Boolean).join(" · ");
    return `<div class="bloque"><span>${(b.repeticiones||1)>1?b.repeticiones+"× ":""}${esc(b.nombre)}</span><span class="sub">${b.duracion_min} min · ${extra}</span></div>`;
  }).join("");
}
function htmlDiaNutricion(dn, abierto){
  const obj = dn.tipo_dia==="entreno"?D.nutricion.kcal_entreno:D.nutricion.kcal_descanso;
  let h = `<div class="card"><h3>${dn.tipo_dia==="entreno"?"Día de entreno":"Día de descanso"}</h3>
    <div class="kcal"><span><b>${r0(dn.totales.kcal)}</b> / ${obj} kcal</span><span>P <b>${r0(dn.totales.proteina_g)}</b> g</span><span>HC <b>${r0(dn.totales.carbohidratos_g)}</b> g</span><span>G <b>${r0(dn.totales.grasa_g)}</b> g</span>${dn.totales.fibra_g?`<span>Fibra <b>${r0(dn.totales.fibra_g)}</b> g</span>`:""}</div>
    <div class="barra"><i style="width:${Math.min(100,dn.totales.kcal/obj*100)}%"></i></div>`;
  dn.comidas.forEach(c=>{
    h += `<div class="comida"><div class="h">${COMIDA[c.comida]||c.comida}<span>${esc(c.hora)}</span></div><ul>`;
    c.items.forEach(it=>{
      if(it.receta_id && recetas[it.receta_id]){
        const r=recetas[it.receta_id];
        h += `<li>${esc(r.nombre)}${it.raciones!==1?` × ${it.raciones}`:""}<details ${abierto?"":""}><summary>Receta · ${r.tiempo_min} min</summary>${htmlReceta(r)}</details></li>`;
      } else h += `<li>${esc(it.alimento)}${it.gramos?` · ${it.gramos} g`:""}</li>`;
    });
    h += `</ul>${c.notas?`<div class="sub">${esc(c.notas)}</div>`:""}</div>`;
  });
  return h+`</div>`;
}
function htmlReceta(r){
  return `<div class="receta"><ul>${r.ingredientes.map(i=>`<li>${esc(i.alimento)} — ${i.gramos} g${i.medida_casera?` (${esc(i.medida_casera)})`:""}</li>`).join("")}</ul>
  <ol>${r.pasos.map(p=>`<li>${esc(p)}</li>`).join("")}</ol>
  <div class="sub">Por ración: ${r0(r.macros_racion.kcal)} kcal · P ${r0(r.macros_racion.proteina_g)} · HC ${r0(r.macros_racion.carbohidratos_g)} · G ${r0(r.macros_racion.grasa_g)}${r.raciones>1?` · rinde ${r.raciones} raciones`:""}${r.conservacion?` · ${esc(r.conservacion)}`:""}</div></div>`;
}
function selectorDias(){
  return `<div class="dias">${P.entrenamiento.dias.map((d,i)=>`<button data-dia="${i}" class="${i===diaSel?"on":""}">${DIAS_CORTOS[d.dia]}<small>${d.fecha.slice(8)}</small></button>`).join("")}</div>`;
}

const VISTAS = {
  "Hoy": ()=>{
    const d = P.entrenamiento.dias[diaSel], dn = P.nutricion.dias[diaSel];
    let h = selectorDias() + `<h2>${NOMBRE_DIA[d.dia]} ${fmtFecha(d.fecha)}</h2>`;
    h += d.sesiones.length ? d.sesiones.map(s=>htmlSesion(s,true)).join("") : `<div class="card"><h3>Descanso</h3><p class="sub">${esc(d.notas||"Día de recuperación: camina, duerme bien y bebe agua.")}</p></div>`;
    return h + htmlDiaNutricion(dn, true);
  },
  "Semana": ()=>`<div class="grid7">${P.entrenamiento.dias.map((d,i)=>{
      const dn=P.nutricion.dias[i];
      return `<div class="card"><h3>${NOMBRE_DIA[d.dia]} <span class="sub">${fmtFecha(d.fecha)}</span></h3>${
        d.sesiones.length? d.sesiones.map(s=>`<div><span class="tag ${s.tipo==="fuerza"?"fuerza":"cardio"}">${s.tipo==="fuerza"?"Fuerza":(CARDIO[s.tipo]||s.tipo)}</span>${s.duracion_min} min · ${esc(s.hora)}</div><div class="sub">${esc(s.tipo==="fuerza"?(rutinas[s.rutina_ref]||{}).titulo:s.objetivo)}</div>`).join("") : `<div class="sub">Descanso</div>`
      }<div class="kcal"><span><b>${r0(dn.totales.kcal)}</b> kcal</span><span>P <b>${r0(dn.totales.proteina_g)}</b> g</span></div></div>`;}).join("")}</div>`,
  "Rutinas": ()=> P.entrenamiento.rutinas.map(r=>htmlSesion({tipo:"fuerza",rutina_ref:r.id,hora:"",duracion_min:"",objetivo:""},false)
      .replace(/<div class="sub"> ·  min · <\/div>/,"")).join(""),
  "Menú": ()=> selectorDias() + htmlDiaNutricion(P.nutricion.dias[diaSel], false)
      + `<div class="card"><h3>Todas las recetas</h3>${P.nutricion.recetas.map(r=>`<details><summary>${esc(r.nombre)} · ${r.tiempo_min} min${r.batch?" · en tanda":""}</summary>${htmlReceta(r)}</details>`).join("")}</div>`
      + (P.nutricion.alimentos_evitar.length?`<div class="card"><h3>Evitar</h3><ul>${P.nutricion.alimentos_evitar.map(x=>`<li><b>${esc(x.alimento_o_grupo)}</b> (${x.nivel}) — ${esc(x.motivo)}</li>`).join("")}</ul></div>`:"")
      + (P.nutricion.hidratacion?`<div class="card"><h3>Hidratación</h3><p>${esc(P.nutricion.hidratacion)}</p></div>`:""),
  "Compra": ()=>{
    const marcados = leer("compra")||{};
    const grupos = {};
    P.nutricion.lista_compra.forEach(x=>(grupos[x.seccion]=grupos[x.seccion]||[]).push(x));
    return `<p class="sub">${P.nutricion.lista_compra.length} productos · marca lo que ya tengas o lo que vayas comprando.</p>` +
      Object.keys(SECCION).filter(s=>grupos[s]).map(s=>`<div class="card sec compra"><h3>${SECCION[s]}</h3><ul>${grupos[s].map(x=>{
        const id=x.alimento; const ok=marcados[id];
        return `<li class="${ok?"hecho":""}"><input type="checkbox" data-compra="${esc(id)}" ${ok?"checked":""}><span>${esc(x.alimento)} — ${x.cantidad} ${x.unidad}</span></li>`;}).join("")}</ul></div>`).join("");
  },
};

let vista = "Hoy";
function pintar(){
  document.getElementById("tabs").innerHTML = Object.keys(VISTAS).map(v=>`<button class="${v===vista?"on":""}" data-vista="${v}">${v}</button>`).join("");
  document.getElementById("main").innerHTML = VISTAS[vista]();
}
document.addEventListener("click", e=>{
  const b = e.target.closest("button");
  if(b?.dataset.vista){ vista=b.dataset.vista; pintar(); window.scrollTo(0,0); }
  else if(b?.dataset.dia){ diaSel=+b.dataset.dia; pintar(); }
});
document.addEventListener("change", e=>{
  const t=e.target;
  if(t.dataset.serie){ const h=leer("series")||{}; h[t.dataset.serie]=t.checked; guardar("series",h); t.closest("tr").classList.toggle("hecho",t.checked); }
  if(t.dataset.compra){ const h=leer("compra")||{}; h[t.dataset.compra]=t.checked; guardar("compra",h); t.closest("li").classList.toggle("hecho",t.checked); }
});
pintar();
</script>
</body>
</html>
"""
