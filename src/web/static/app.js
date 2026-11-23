// Pantallas de la aplicación web. Los datos vienen de la API (src/web/rutas_*.py), que usa los
// mismos servicios del sistema: acá no hay reglas de negocio, solo se muestran datos y se envían pedidos.

// ---------- utilidades ----------
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $$ = n => { const v = Number(n || 0); return (v < 0 ? '-' : '') + '$ ' + Math.abs(v).toLocaleString('es-AR', {minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2}); };
const num = n => Number(n || 0).toLocaleString('es-AR');
const p2 = n => String(n).padStart(2, '0');
const aFecha = s => { if (!s) return null; if (s instanceof Date) return s; return /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(s + 'T00:00') : new Date(s); };
const fh = s => { const d = aFecha(s); return d ? `${p2(d.getDate())}/${p2(d.getMonth()+1)} ${p2(d.getHours())}:${p2(d.getMinutes())}` : '—'; };
const fd = s => { const d = aFecha(s); return d ? `${p2(d.getDate())}/${p2(d.getMonth()+1)}/${d.getFullYear()}` : '—'; };
const iso = d => `${d.getFullYear()}-${p2(d.getMonth()+1)}-${p2(d.getDate())}`;
const haceDias = n => { const d = new Date(); d.setDate(d.getDate() - n); return d; };
const KIND = {'Verificado':'ok','Recibida':'ok','Cerrada completa':'ok','Normal':'ok','Activo':'ok','Activa':'ok','Abierta':'ok','Consolidada':'ok',
  'Rechazado':'bad','Bajo el mínimo':'bad','Cerrada':'n','Anulada':'n','Dado de baja':'n','Dada de baja':'n','Despachada':'n','Recibido':'n',
  'En tránsito':'warn','Pendiente':'warn','En el mínimo':'warn','Cerrada con faltantes':'warn','Preparado':'warn','Emitido':'warn','En preparación':'warn','Verificado con rechazos':'warn'};
const pill = t => `<span class="pill ${KIND[t]||''}">${esc(t)}</span>`;
function toast(msg, kind=''){ const t = document.getElementById('toast'); const d = document.createElement('div'); d.className = kind; d.textContent = msg; t.appendChild(d); setTimeout(() => d.remove(), 6000); }
const err = m => { toast(m, 'bad'); return 'ERR'; };
const tabla = (cols, filas, pie='') => `<div class="tw"><table><thead><tr>${cols.map(c=>`<th class="${c[1]||''}">${c[0]}</th>`).join('')}</tr></thead><tbody>${filas.join('') || `<tr><td colspan="${cols.length}" class="muted">Sin datos para los filtros elegidos.</td></tr>`}</tbody>${pie?`<tfoot>${pie}</tfoot>`:''}</table></div>`;
const hbars = items => { const mx = Math.max(1, ...items.map(i=>i.v)); return items.map(i=>`<div class="hbar"><div class="t"><span style="font-weight:500">${esc(i.l)}</span><span>${esc(i.t)}</span></div><div class="track"><i style="width:${Math.round(i.v/mx*100)}%;${i.alerta?'background:var(--warn-dot)':''}"></i></div></div>`).join('') || '<div class="muted">Sin datos para graficar.</div>'; };
const tabs = (g, items) => `<div class="tabs" role="tablist">${items.map(([k,l])=>`<button role="tab" aria-selected="${ui.tab[g]===k}" class="${ui.tab[g]===k?'on':''}" data-a="tab" data-g="${g}" data-k="${k}">${l}</button>`).join('')}</div>`;
const opts = (items, sel) => items.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(sel)?'selected':''}>${esc(l)}</option>`).join('');
const coincide = (q, ...txt) => !q || txt.join(' ').toLowerCase().includes(q.trim().toLowerCase());
const val = id => { const el = document.getElementById(id); return el ? el.value.trim() : ''; };

// filtros: data-f guarda el valor en ui.f y redibuja; data-fr además vuelve a pedir los datos al servidor
const F = (k, c, def='') => { const g = ui.f[k]; return g && g[c] !== undefined ? g[c] : def; };
const fTxt = (k, c, ph, w=220) => `<input class="in" type="search" id="f-${k}-${c}" data-f="${k}.${c}" placeholder="${ph}" aria-label="${ph}" value="${esc(F(k,c))}" style="flex:1 1 ${w}px">`;
const fSel = (k, c, label, items, def='', recarga=false) => `<div class="fs"><label class="lab" for="f-${k}-${c}">${label}</label><select class="in" id="f-${k}-${c}" data-f="${k}.${c}" ${recarga?'data-fr="1"':''}>${opts(items, F(k,c,def))}</select></div>`;
const fDate = (k, c, label, def) => `<div class="fs"><label class="lab" for="f-${k}-${c}">${label}</label><input class="in" type="date" id="f-${k}-${c}" data-f="${k}.${c}" data-fr="1" value="${F(k,c,def)}"></div>`;

// ---------- comunicación con la API ----------
async function api(url, metodo='GET', datos){
  const r = await fetch(url, {method: metodo, headers: datos ? {'Content-Type':'application/json'} : {}, body: datos ? JSON.stringify(datos) : undefined});
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((j && j.error) || `Error ${r.status} del servidor.`);
  return j;
}
const post = (url, datos={}) => api(url, 'POST', datos);

// catálogo: nombres de ubicaciones, productos, etc. Se recarga después de cada cambio en Administración.
let C = {ubicaciones:[], categorias:[], productos:[], proveedores:[], clientes:[], datos:{}};
const IDX = {};
async function cargarCatalogo(){
  C = await api('/api/catalogo');
  for (const k of ['ubicaciones','categorias','productos','proveedores','clientes']) IDX[k] = Object.fromEntries(C[k].map(x=>[x.id, x]));
}
const prod = id => IDX.productos[id] || {nombre:`Producto ${id}`, sku:'', costo:0, precio:0};
const nomProd = id => prod(id).nombre;
const nomUbi = id => (IDX.ubicaciones[id] || {nombre:`Ubicación ${id}`}).nombre;
const nomProv = id => (IDX.proveedores[id] || {razon_social:`Proveedor ${id}`}).razon_social;
const sucs = () => C.ubicaciones.filter(u=>u.tipo==='SUCURSAL' && u.activa);
const ubis = () => C.ubicaciones.filter(u=>u.activa);
const activos = () => C.productos.filter(p=>p.activo);
const optSuc = todas => [...(todas?[['','Todas']]:[]), ...sucs().map(s=>[s.id, s.nombre])];
const optUbi = todas => [...(todas?[['','Todas']]:[]), ...ubis().map(s=>[s.id, s.nombre])];
const optCat = () => [['','Todas'], ...C.categorias.map(c=>[c.id, c.nombre])];
const itemsTxt = its => its.map(i=>`${num(i.cantidad ?? i.solicitada)} × ${esc(nomProd(i.producto_id))}`).join('<br>');
const estadoStock = (d, m) => !m ? 'Normal' : d < m ? 'Bajo el mínimo' : d === m ? 'En el mínimo' : 'Normal';
const IVA = [['CONSUMIDOR_FINAL','Consumidor final'],['RESPONSABLE_INSCRIPTO','Responsable inscripto'],['MONOTRIBUTISTA','Monotributista'],['EXENTO','Exento']];
const nomIva = k => (IVA.find(x=>x[0]===k)||[k,k])[1];
const MEDIOS = [['EFECTIVO','Efectivo'],['DEBITO','Débito'],['CREDITO','Crédito'],['TRANSFERENCIA','Transferencia']];
const nomMedio = k => (MEDIOS.find(x=>x[0]===k)||[k,k])[1];
const cuit = c => c && c.length===11 ? `${c.slice(0,2)}-${c.slice(2,10)}-${c.slice(10)}` : c;

// ---------- estado de la pantalla ----------
const ui = { view:'inicio', tab:{administracion:'productos', inventario:'stock', logistica:'armado', ventas:'nueva'}, f:{}, d:null, abm:{}, modal:null,
  cart:[], pagos:[], oc:[], nd:[], arm:[], bulto:null, rep:'r6', devVenta:null, movSku:null, ordSel:null, ocupado:false };
const VISTAS = [['inicio','Inicio','M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z'],['administracion','Administración','M4 6h16M4 12h16M4 18h10'],['inventario','Inventario','M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8'],['logistica','Logística','M2 7h11v9H2zM13 10h5l4 3v3h-9zM6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'],['ventas','Ventas','M3 4h2l2.5 11h10L20 7H6.5M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM17 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2z'],['reportes','Reportes','M4 20V10M10 20V4M16 20v-7M22 20H2']];
const sucVenta = () => { const v = F('ven','suc'); return sucs().some(s=>String(s.id)===String(v)) ? Number(v) : (sucs()[0]||{}).id; };
const ubicStock = () => { const v = F('inv','ubic'); return ubis().some(s=>String(s.id)===String(v)) ? Number(v) : ((sucs()[0]||ubis()[0])||{}).id; };

// ---------- carga de datos de cada pantalla ----------
async function cargarDatos(){
  const t = ui.tab[ui.view];
  if (ui.view==='inicio') return api('/api/inicio');
  if (ui.view==='inventario') {
    if (t==='stock') return ubicStock() ? api(`/api/stock?ubicacion=${ubicStock()}`) : {filas:[], movimientos:[], alertas:[]};
    return api({compras:'/api/compras', necesidades:'/api/necesidades', ordenes:'/api/ordenes'}[t]);
  }
  if (ui.view==='logistica') {
    if (t==='trazabilidad') { const bultos = await api('/api/bultos'); const b = bultos.find(x=>x.id===ui.bulto) || bultos[0];
      return {bultos, historial: b ? await api(`/api/bultos/${b.id}/historial`) : []}; }
    return api('/api/logistica');
  }
  if (ui.view==='ventas') { const s = sucVenta(); if (!s) return {};
    if (t==='devoluciones') { const [ventas, devs] = await Promise.all([api(`/api/ventas/devolvibles?sucursal=${s}`), api(`/api/devoluciones?sucursal=${s}`)]);
      if (!ventas.some(v=>v.id===ui.devVenta)) ui.devVenta = null;
      return {ventas, devs, renglones: ui.devVenta ? await api(`/api/ventas/${ui.devVenta}/renglones`) : []}; }
    if (t==='clientes') return {};
    return api(`/api/ventas/contexto?sucursal=${s}`);
  }
  if (ui.view==='reportes') return api(`/api/reportes/${ui.rep}?${consultaReporte()}`);
  return {};
}
async function refrescar(){ try { ui.d = await cargarDatos(); } catch (e) { ui.d = null; err(e.message); } render(); }

// ---------- altas, bajas y modificaciones (Administración y clientes) ----------
const ABM = {
  ubicaciones: { lista:()=>C.ubicaciones, uno:'ubicación', una:true, titulo:'sucursales y CD', url:'/api/ubicaciones', baja:'logica', activo:'activa',
    cols:[['Código',x=>x.codigo],['Nombre',x=>x.nombre],['Tipo',x=>x.tipo==='CD'?'Centro de Distribución':'Sucursal'],['Dirección',x=>x.direccion],['Teléfono',x=>x.telefono],['Punto de venta',x=>x.punto_venta??'—','r']],
    campos:[['codigo','Código'],['nombre','Nombre'],['tipo','Tipo',()=>[['SUCURSAL','Sucursal'],['CD','Centro de Distribución']],'alta'],['punto_venta','Punto de venta (solo sucursales)','num'],['direccion','Dirección'],['telefono','Teléfono']],
    nuevo:()=>({tipo:'SUCURSAL', punto_venta: Math.max(0, ...C.ubicaciones.map(u=>u.punto_venta||0)) + 1}),
    filtros:()=>fSel('ubicaciones','tipo','Tipo',[['','Todos'],['SUCURSAL','Sucursal'],['CD','Centro de Distribución']]), pasa:x=>!F('ubicaciones','tipo')||x.tipo===F('ubicaciones','tipo'),
    nota:'El sistema trabaja con un solo Centro de Distribución activo. Cada sucursal tiene su propio punto de venta para numerar comprobantes.' },
  categorias: { lista:()=>C.categorias, uno:'categoría', una:true, titulo:'categorías', url:'/api/categorias', baja:'borrar',
    cols:[['Categoría',x=>x.nombre],['Descripción',x=>x.descripcion],['Productos',x=>C.productos.filter(p=>p.categoria_id===x.id).length,'r']],
    campos:[['nombre','Nombre'],['descripcion','Descripción']], nota:'Una categoría solo se puede eliminar si no tiene productos.' },
  productos: { lista:()=>C.productos, uno:'producto', titulo:'productos', url:'/api/productos', baja:'logica', activo:'activo', detalle:true,
    cols:[['SKU',x=>x.sku],['Producto',x=>x.nombre],['Categoría',x=>(IDX.categorias[x.categoria_id]||{}).nombre],['Proveedores',x=>x.proveedores.map(nomProv).join(', ')||'—'],['Costo',x=>$$(x.costo),'r'],['Precio',x=>$$(x.precio),'r'],['Margen',x=>x.costo>0?Math.round((x.precio-x.costo)/x.costo*100)+' %':'—','r']],
    campos:[['nombre','Nombre'],['sku','SKU'],['categoria_id','Categoría',()=>C.categorias.map(c=>[c.id,c.nombre])],['costo','Costo','num'],['precio','Precio de venta','num']],
    filtros:()=>fSel('productos','cat','Categoría',optCat()) + fSel('productos','prov','Proveedor',[['','Todos'],...C.proveedores.map(p=>[p.id,p.razon_social])]),
    pasa:x=>(!F('productos','cat')||String(x.categoria_id)===F('productos','cat')) && (!F('productos','prov')||x.proveedores.map(String).includes(F('productos','prov'))),
    extra:(x, det)=>`<div class="lab">Proveedores</div><div class="chk">${C.proveedores.filter(p=>p.activo || (x && x.proveedores.includes(p.id))).map(p=>`<label><input type="checkbox" class="pp" value="${p.id}" ${x && x.proveedores.includes(p.id)?'checked':''}> ${esc(p.razon_social)}</label>`).join('')}</div>
      <div class="lab">Stock mínimo por ubicación</div><div class="ctl">${ubis().map(u=>`<div class="f"><label for="m-${u.id}">${esc(u.codigo)}</label><input class="in" id="m-${u.id}" type="number" min="0" value="${det?(det.minimos[u.id]||0):0}"></div>`).join('')}</div>` +
      (det && det.historial.length ? `<div class="note"><b>Historial de precios</b>${det.historial.map(h=>`<div class="sum"><span>${fd(h.desde)}${h.hasta?'':' · vigente'}</span><span>costo ${$$(h.costo)} · precio ${$$(h.precio)}</span></div>`).join('')}</div>` : ''),
    datosExtra:()=>({proveedores:[...document.querySelectorAll('.pp:checked')].map(x=>Number(x.value)), minimos:Object.fromEntries(ubis().map(u=>[u.id, Number(val('m-'+u.id)||0)]))}),
    nota:'El margen es lo que se gana sobre el costo: (precio − costo) ÷ costo. Cada cambio de costo o precio queda en el historial.' },
  proveedores: { lista:()=>C.proveedores, uno:'proveedor', titulo:'proveedores', url:'/api/proveedores', baja:'logica', activo:'activo',
    cols:[['CUIT',x=>cuit(x.cuit)],['Razón social',x=>x.razon_social],['Email',x=>x.email],['Teléfono',x=>x.telefono],['Productos',x=>C.productos.filter(p=>p.proveedores.includes(x.id)).length,'r']],
    campos:[['cuit','CUIT (11 dígitos)'],['razon_social','Razón social'],['email','Email'],['telefono','Teléfono'],['direccion','Dirección']],
    nota:'El CUIT identifica al proveedor: no puede repetirse y se valida su dígito verificador.' },
  clientes: { lista:()=>C.clientes, uno:'cliente', titulo:'clientes', url:'/api/clientes',
    cols:[['Documento o CUIT',x=>x.documento],['Nombre',x=>x.nombre],['Condición frente al IVA',x=>nomIva(x.condicion_iva)]],
    campos:[['documento','Documento o CUIT'],['nombre','Nombre o razón social'],['condicion_iva','Condición frente al IVA',()=>IVA]],
    filtros:()=>fSel('clientes','iva','Condición',[['',"Todas"],...IVA]), pasa:x=>!F('clientes','iva')||x.condicion_iva===F('clientes','iva'),
    nota:'La condición frente al IVA define el comprobante: Factura A para responsables inscriptos, Factura B para el resto de los clientes identificados y Ticket para consumidor final.' },
};
const estadoAbm = (c, x) => c.activo ? (x[c.activo] ? (c.una?'Activa':'Activo') : (c.una?'Dada de baja':'Dado de baja')) : '';
function abmView(e){
  const c = ABM[e], L = c.lista(), q = F(e,'q'), est = F(e,'estado','activos');
  const filas = L.filter(it=>coincide(q, ...c.cols.map(k=>k[1](it))) && (!c.activo || est==='todos' || (est==='activos')===!!it[c.activo]) && (!c.pasa || c.pasa(it)))
    .map(it=>`<tr>${c.cols.map((k,j)=>`<td class="${k[2]||''}">${j===1?`<b style="font-weight:500">${esc(k[1](it))}</b>`:esc(k[1](it))}</td>`).join('')}${c.activo?`<td>${pill(estadoAbm(c,it))}</td>`:''}<td class="r"><button class="btn s" data-a="abmEdit" data-e="${e}" data-id="${it.id}">Editar</button></td></tr>`);
  return `<section class="card"><div class="bar">${fTxt(e,'q','Buscar en '+c.titulo)}${c.filtros?c.filtros():''}${c.activo?fSel(e,'estado','Estado',[['activos',c.una?'Activas':'Activos'],['bajas',c.una?'Dadas de baja':'Dados de baja'],['todos','Todos']],'activos'):''}</div>
      ${tabla([...c.cols.map(k=>[k[0],k[2]||'']),...(c.activo?[['Estado']]:[]),['']], filas)}<div class="muted">${filas.length} de ${L.length} registros.</div></section>`;
}
const btnAlta = e => `<button class="btn p" data-a="abmNuevo" data-e="${e}">Agregar ${ABM[e].uno}</button>`;
function mAbm(e){
  const c = ABM[e], x = c.lista().find(o=>o.id===ui.abm[e]) || null, base = x || (c.nuevo ? c.nuevo() : {});
  const campo = ([k,l,t,cuando]) => { const id = `a-${e}-${k}`, v = base[k] ?? '';
    if (cuando==='alta' && x) return `<div class="f"><label>${l}</label><input class="in" value="${esc((t()).find(o=>String(o[0])===String(v))?.[1]||v)}" readonly></div>`;
    if (typeof t==='function') return `<div class="f"><label for="${id}">${l}</label><select class="in" id="${id}">${opts(t(), v)}</select></div>`;
    return `<div class="f"><label for="${id}">${l}</label><input class="in" id="${id}" ${t==='num'?'type="number" min="0"':''} value="${esc(v)}"></div>`; };
  const baja = !x ? '' : c.baja==='borrar' ? `<button class="btn" data-a="abmBaja" data-e="${e}" style="flex:1 1 120px">Eliminar</button>`
    : c.baja==='logica' ? `<button class="btn" data-a="abmBaja" data-e="${e}" style="flex:1 1 120px">${x[c.activo]?'Dar de baja':'Reactivar'}</button>` : '';
  return [x ? 'Editar '+c.uno : 'Agregar '+c.uno, `<div class="ctl">${c.campos.map(campo).join('')}</div>${c.extra?c.extra(x, ui.modal.det):''}${c.nota?`<div class="note">${c.nota}</div>`:''}
      <div class="ctl"><button class="btn p" data-a="abmGuardar" data-e="${e}" style="flex:2 1 140px">Guardar</button>${baja}<button class="btn" data-a="cerrar" style="flex:1 1 100px">Cancelar</button></div>`];
}

// ---------- ventanas de alta de compras y necesidades ----------
function mOc(){ const pa = C.proveedores.filter(p=>p.activo), prov = pa.some(p=>String(p.id)===F('oc','prov')) ? Number(F('oc','prov')) : (pa[0]||{}).id;
  const ps = activos().filter(p=>p.proveedores.includes(prov));
  return ['Nueva orden de compra', `<div class="muted">Destino: ${esc((C.ubicaciones.find(u=>u.tipo==='CD'&&u.activa)||{nombre:'Centro de Distribución'}).nombre)}</div>
        <div class="f"><label for="f-oc-prov">Proveedor</label><select class="in" id="f-oc-prov" data-f="oc.prov">${opts(pa.map(p=>[p.id,p.razon_social]), prov)}</select></div>
        <button class="btn" data-a="ocSugerir">Sugerir según faltantes del CD</button>
        <div class="ctl" style="align-items:flex-end"><div class="f" style="flex:2 1 180px"><label for="oc-sku">Producto</label><select class="in" id="oc-sku">${opts(ps.map(p=>[p.id, `${p.nombre} (costo ${$$(p.costo)})`]), '')}</select></div>
          <div class="f" style="flex:1 1 80px"><label for="oc-cant">Cantidad</label><input class="in" id="oc-cant" type="number" min="1" value="12"></div>
          <div class="f" style="flex:1 1 90px"><label for="oc-costo">Costo unit.</label><input class="in" id="oc-costo" type="number" min="0" placeholder="actual"></div></div>
        ${ps.length ? '' : '<div class="note warn">Este proveedor no tiene productos asignados. Asignáselos en Administración → Productos.</div>'}
        <button class="btn" data-a="ocAdd">Agregar producto</button>
        ${ui.oc.map((i,k)=>`<div class="sum"><span>${num(i.cantidad)} × ${esc(nomProd(i.producto_id))} a ${$$(i.costo)}</span><span>${$$(i.cantidad*i.costo)} <button class="btn s" data-a="ocQuitar" data-i="${k}">Quitar</button></span></div>`).join('') || '<div class="muted">Todavía no hay productos en la orden.</div>'}
        <div class="sum" style="border-top:1px solid var(--line);padding-top:12px"><span>Total de la orden</span><span class="big">${$$(ui.oc.reduce((a,i)=>a+i.cantidad*i.costo,0))}</span></div>
        <div class="ctl"><button class="btn p" data-a="ocCrear" style="flex:2 1 160px">Crear orden de compra</button><button class="btn" data-a="cerrar" style="flex:1 1 100px">Cancelar</button></div>`]; }
function mNd(){ const sn = sucs().some(s=>String(s.id)===F('nec','sucN')) ? Number(F('nec','sucN')) : (sucs()[0]||{}).id;
  return ['Nueva necesidad de reposición', `<div class="f"><label for="f-nec-sucN">Sucursal que pide</label><select class="in" id="f-nec-sucN" data-f="nec.sucN">${opts(optSuc(false), sn)}</select></div>
        <button class="btn" data-a="ndSugerir">Sugerir según stock mínimo</button>
        <div class="ctl" style="align-items:flex-end"><div class="f" style="flex:2 1 180px"><label for="nd-sku">Producto</label><select class="in" id="nd-sku">${opts(activos().map(p=>[p.id, `${p.nombre} (${p.sku})`]), '')}</select></div>
          <div class="f" style="flex:1 1 80px"><label for="nd-cant">Cantidad</label><input class="in" id="nd-cant" type="number" min="1" value="6"></div></div>
        <button class="btn" data-a="ndAdd">Agregar producto</button>
        ${ui.nd.map((i,k)=>`<div class="sum"><span>${num(i.cantidad)} × ${esc(nomProd(i.producto_id))}</span><button class="btn s" data-a="ndQuitar" data-i="${k}">Quitar</button></div>`).join('') || '<div class="muted">Todavía no hay productos.</div>'}
        <div class="ctl"><button class="btn p" data-a="ndCrear" style="flex:2 1 160px">Registrar necesidad</button><button class="btn" data-a="cerrar" style="flex:1 1 100px">Cancelar</button></div>`]; }
function modal(){ const m = ui.modal; if (!m) return ''; const [t, cuerpo] = m.t==='abm' ? mAbm(m.e) : m.t==='oc' ? mOc() : mNd();
  return `<div class="ov"><div class="card dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t"><h2 id="dlg-t">${t}</h2>${cuerpo}</div></div>`; }
function sumar(lista, item){ const it = lista.find(i=>i.producto_id===item.producto_id); if (it) it.cantidad += item.cantidad; else lista.push(item); }

// ---------- acciones ----------
async function enviar(fn, {ok, catalogo=false, cerrar=true}={}){
  try { const r = await fn(); if (catalogo) await cargarCatalogo(); if (cerrar) ui.modal = null;
    if (ok) toast(typeof ok==='function' ? ok(r) : ok, 'ok'); await refrescar(); return 'HECHO'; }
  catch (e) { return err(e.message); }
}
const A = {
  tab(d){ ui.tab[d.g] = d.k; ui.modal = null; return refrescar().then(()=>'HECHO'); },
  go(d){ location.hash = d.v; return 'HECHO'; },
  cerrar(){ ui.modal = null; },
  modal(d){ ui.modal = {t:d.m}; if (d.m==='oc') ui.oc = []; if (d.m==='nd') ui.nd = []; },
  // Administración
  async abmEdit(d){ const c = ABM[d.e]; ui.abm[d.e] = Number(d.id); let det = null;
    if (c.detalle) { try { det = await api(`${c.url}/${d.id}`); } catch (e) { return err(e.message); } }
    ui.modal = {t:'abm', e:d.e, det}; },
  abmNuevo(d){ ui.abm[d.e] = null; ui.modal = {t:'abm', e:d.e, det:null}; },
  abmGuardar(d){ const c = ABM[d.e], id = ui.abm[d.e], datos = {};
    for (const [k,,t,cuando] of c.campos) { if (cuando==='alta' && id) continue; datos[k] = val(`a-${d.e}-${k}`); }
    Object.assign(datos, c.datosExtra ? c.datosExtra() : {});
    return enviar(() => api(id ? `${c.url}/${id}` : c.url, id ? 'PUT' : 'POST', datos),
      {catalogo:true, ok: id ? 'Cambios guardados.' : `Se agregó ${c.una?'la':'el'} ${c.uno}.`}); },
  abmBaja(d){ const c = ABM[d.e], id = ui.abm[d.e], x = c.lista().find(o=>o.id===id);
    if (c.baja==='borrar') return enviar(() => api(`${c.url}/${id}`, 'DELETE'), {catalogo:true, ok:`Se eliminó la ${c.uno}.`});
    const activo = x[c.activo];
    return enviar(() => post(`${c.url}/${id}/${activo?'baja':'reactivar'}`), {catalogo:true, ok: activo ? 'Dado de baja. Se puede reactivar desde el filtro de estado.' : 'Reactivado.'}); },
  // Datos de prueba
  datosPrueba(d){ return enviar(() => post(`/api/datos-prueba/${d.paso}`), {catalogo:true, ok:'Datos de prueba cargados.'}); },
  // Inventario
  verMov(d){ ui.movSku = ui.movSku===Number(d.id) ? null : Number(d.id); },
  descartar(d){ return enviar(() => post('/api/alertas/descartar', {producto_id:Number(d.id), ubicacion_id:ubicStock()})); },
  ocAdd(){ const id = Number(val('oc-sku')), cant = Math.floor(Number(val('oc-cant'))), costo = Number(val('oc-costo')) || prod(id).costo;
    if (!id) return err('Elegí un producto del proveedor.'); if (!(cant>0)) return err('La cantidad debe ser mayor que cero.'); if (!(costo>0)) return err('El costo debe ser mayor que cero.');
    sumar(ui.oc, {producto_id:id, cantidad:cant, costo}); },
  ocQuitar(d){ ui.oc.splice(Number(d.i),1); },
  async ocSugerir(){ const prov = Number(val('f-oc-prov')); try { const r = await api(`/api/compras/sugerencia?proveedor=${prov}`);
      if (!r.length) return err('El CD no tiene faltantes de productos de este proveedor.'); ui.oc = r; toast(`Se cargaron ${r.length} producto(s) que están en su mínimo en el CD.`, 'ok'); } catch (e) { return err(e.message); } },
  ocCrear(){ if (!ui.oc.length) return err('Agregá al menos un producto a la orden.');
    return enviar(() => post('/api/compras', {proveedor_id:Number(val('f-oc-prov')), renglones:ui.oc}), {ok:r=>`Orden de compra N° ${r.numero} creada. Queda pendiente hasta recibirla en el CD.`}); },
  recibirOC(d){ return enviar(() => post(`/api/compras/${d.id}/recibir`), {ok:r=>`Orden N° ${r.numero} recibida: el stock ingresó al Centro de Distribución.`}); },
  anularOC(d){ return enviar(() => post(`/api/compras/${d.id}/anular`), {ok:r=>`Orden N° ${r.numero} anulada.`}); },
  ndAdd(){ const id = Number(val('nd-sku')), cant = Math.floor(Number(val('nd-cant')));
    if (!id) return err('Elegí un producto.'); if (!(cant>0)) return err('La cantidad debe ser mayor que cero.'); sumar(ui.nd, {producto_id:id, cantidad:cant}); },
  ndQuitar(d){ ui.nd.splice(Number(d.i),1); },
  async ndSugerir(){ const s = Number(val('f-nec-sucN')); try { const r = await api(`/api/necesidades/sugerencia?sucursal=${s}`);
      if (!r.length) return err('Esa sucursal no tiene productos en su stock mínimo (o ya vienen en camino).'); ui.nd = r; toast(`Se cargaron ${r.length} producto(s) en su mínimo.`, 'ok'); } catch (e) { return err(e.message); } },
  ndCrear(){ if (!ui.nd.length) return err('Agregá al menos un producto a la necesidad.');
    return enviar(() => post('/api/necesidades', {sucursal_id:Number(val('f-nec-sucN')), renglones:ui.nd}), {ok:r=>`Necesidad N° ${r.id} registrada.`}); },
  necAnular(d){ return enviar(() => post(`/api/necesidades/${d.id}/anular`), {ok:`Necesidad N° ${d.id} anulada.`}); },
  necOrden(d){ return enviar(() => post('/api/necesidades/consolidar', {ids:[Number(d.id)]}), {ok:r=>{ ui.tab.inventario = 'ordenes'; ui.ordSel = r.id; return `Se creó la orden de reposición N° ${r.numero}.`; }}); },
  consolidar(){ const suc = F('nec','suc'); if (!suc) return err('Elegí una sucursal en el filtro para consolidar todas sus necesidades pendientes.');
    const ids = (ui.d||[]).filter(n=>String(n.sucursal_id)===suc && n.estado==='PENDIENTE').map(n=>n.id); if (!ids.length) return err('Esa sucursal no tiene necesidades pendientes.');
    return enviar(() => post('/api/necesidades/consolidar', {ids}), {ok:r=>{ ui.tab.inventario = 'ordenes'; ui.ordSel = r.id; return `Se creó la orden N° ${r.numero} con ${ids.length} necesidad(es).`; }}); },
  ordVer(d){ ui.ordSel = Number(d.id); },
  iniciar(d){ return enviar(() => post(`/api/ordenes/${d.id}/iniciar`), {ok:r=>`Orden N° ${r.numero} en preparación. Seguí en Logística → Armado y despacho.`}); },
  // Logística
  armAdd(){ const o = ordenArmado(), id = Number(val('arm-sku')), cant = Math.floor(Number(val('arm-cant')));
    if (!id) return err('Elegí un producto pendiente.'); if (!(cant>0)) return err('La cantidad debe ser mayor que cero.');
    const ya = (ui.arm.find(i=>i.producto_id===id)||{cantidad:0}).cantidad, it = o.items.find(i=>i.producto_id===id);
    if (cant+ya > it.solicitada-it.preparada) return err(`Solo quedan ${it.solicitada-it.preparada-ya} unidades pendientes de empaquetar.`);
    sumar(ui.arm, {producto_id:id, cantidad:cant}); },
  armTodo(){ const o = ordenArmado(); ui.arm = o.items.map(i=>({producto_id:i.producto_id, cantidad:i.solicitada-i.preparada})).filter(i=>i.cantidad>0);
    if (!ui.arm.length) return err('La orden ya está empaquetada por completo.'); },
  armQuitar(d){ ui.arm.splice(Number(d.i),1); },
  armConfirmar(){ const o = ordenArmado(); if (!ui.arm.length) return err('Agregá al menos un producto al bulto.');
    return enviar(() => post(`/api/ordenes/${o.id}/bultos`, {renglones:ui.arm, precinto:val('arm-prec')}), {ok:r=>{ ui.arm = []; return `Bulto ${r.bulto} armado en el remito ${r.remito} (${r.estado}).`; }}); },
  precintar(d){ return enviar(() => post(`/api/bultos/${d.id}/precintar`, {precinto:val('prec-'+d.id)}), {ok:r=>`${r.bulto} precintado con ${r.precinto}.`}); },
  despachar(d){ return enviar(() => post(`/api/remitos/${d.id}/despachar`, {transportista:val('tr-'+d.id), patente:val('pa-'+d.id)}),
    {ok:'Remito despachado. La mercadería queda pendiente en la sucursal hasta verificar los precintos.'}); },
  recibir(d){ return enviar(() => post(`/api/remitos/${d.id}/recibir`, {recibido_por:val('rp-'+d.id)}), {ok:'Llegada registrada. Ahora controlá el precinto de cada bulto.'}); },
  controlar(d){ return enviar(() => post(`/api/recepciones/${d.rec}/controles`, {bulto_id:Number(d.id), precinto_leido:val('lei-'+d.id), integro:val('est-'+d.id)==='ok', observacion:val('obs-'+d.id)}),
    {ok:r=>`Bulto controlado: ${r.resultado}.`}); },
  cerrarRecepcion(d){ return enviar(() => post(`/api/recepciones/${d.rec}/cerrar`), {ok:r=>`Recepción cerrada: remito ${r.remito} ${r.estado.toLowerCase()}. El stock ya se actualizó.`}); },
  verBulto(d){ ui.bulto = Number(d.id); ui.tab.logistica = 'trazabilidad'; return refrescar().then(()=>'HECHO'); },
  // Ventas
  agregar(d){ const id = Number(d.id), disp = (ui.d.disponible||{})[id] || 0, it = ui.cart.find(i=>i.producto_id===id);
    if ((it?it.cantidad:0)+1 > disp) return err(`No hay más stock disponible de ${nomProd(id)} en esta sucursal.`);
    it ? it.cantidad++ : ui.cart.push({producto_id:id, cantidad:1}); ui.pagos = []; },
  menos(d){ const it = ui.cart.find(i=>i.producto_id===Number(d.id)); if (--it.cantidad<=0) ui.cart = ui.cart.filter(i=>i!==it); ui.pagos = []; },
  pago(){ const medio = val('p-medio'), monto = Number(val('p-monto')), cuotas = medio==='CREDITO' ? Number(val('p-cuotas')) : 1, resta = subtotal()-pagado();
    if (!(monto>0)) return err('El importe del pago debe ser mayor que cero.'); if (monto > resta + 0.001) return err(`El pago supera lo que falta cobrar (${$$(resta)}).`);
    ui.pagos.push({medio, monto, cuotas}); },
  quitarPago(d){ ui.pagos.splice(Number(d.i),1); },
  confirmar(){ if (!ui.cart.length) return err('Agregá al menos un producto.');
    return enviar(() => post('/api/ventas', {sucursal_id:sucVenta(), items:ui.cart, pagos:ui.pagos, cliente_id:F('ven','cli')||null, vendedor:F('ven','vendedor')}),
      {ok:r=>{ ui.cart = []; ui.pagos = []; return `Venta registrada: ${r.comprobante} por ${$$(r.total)}.` + (r.alertas.length ? ' ' + r.alertas.join(' ') : ''); }}); },
  devElegir(d){ ui.devVenta = Number(d.id); return refrescar().then(()=>'HECHO'); },
  devolver(){ const motivo = val('d-motivo'), vuelve = document.getElementById('d-reingresa')?.checked;
    const detalles = (ui.d.renglones||[]).map(r=>({detalle_venta_id:r.id, cantidad:Math.floor(Number(val('d-q'+r.id))||0), reingresa_stock:vuelve})).filter(x=>x.cantidad>0);
    if (!detalles.length) return err('Indicá cuántas unidades se devuelven.');
    return enviar(() => post('/api/devoluciones', {venta_id:ui.devVenta, motivo, detalles}), {ok:'Devolución registrada con su nota de crédito.'}); },
  abrirCaja(){ return enviar(() => post('/api/caja/abrir', {sucursal_id:sucVenta(), saldo_inicial:val('c-inicial')}), {ok:'Caja abierta.'}); },
  cerrarCaja(){ return enviar(() => post('/api/caja/cerrar', {sucursal_id:sucVenta()}), {ok:r=>`Caja cerrada con un saldo de ${$$(r.saldo)}.`}); },
  // Reportes
  rep(d){ ui.rep = d.k; return refrescar().then(()=>'HECHO'); },
};
const subtotal = () => ui.cart.reduce((a,i)=>a+prod(i.producto_id).precio*i.cantidad,0);
const pagado = () => ui.pagos.reduce((a,p)=>a+p.monto,0);
const recargo = p => p.medio==='CREDITO' ? Math.round(p.monto*0.03*(p.cuotas-1)*100)/100 : 0;
const ordenArmado = () => { const os = (ui.d && ui.d.ordenes) || []; return os.find(o=>String(o.id)===F('arm','orden')) || os[0]; };
const ON = { 'ven.suc':()=>{ ui.cart = []; ui.pagos = []; ui.devVenta = null; }, 'oc.prov':()=>{ ui.oc = []; }, 'nec.sucN':()=>{ ui.nd = []; }, 'arm.orden':()=>{ ui.arm = []; }, 'inv.ubic':()=>{ ui.movSku = null; } };

// ---------- vistas ----------
const cabecera = (t, s, der='') => `<header class="head"><div><h1>${t}</h1><div class="sub">${s}</div></div><div class="ctl">${der}</div></header>`;

function vInicio(){
  const d = ui.d || {}, ds = C.datos || {};
  const pasos = [['maestros','1. Datos base','Sucursales, CD, categorías, proveedores, 23 productos con precios y stock mínimo, y 3 clientes.'],
    ['stock','2. Stock inicial','Compras recibidas en el CD y stock verificado en cada sucursal.'],['logistica','3. Logística','Remitos despachados: uno verificado, uno con rechazos y uno en tránsito para recibir.']];
  const prox = pasos.find(p=>!ds[p[0]]);
  const prueba = prox ? `<section class="card"><div class="head"><h2>Datos de prueba</h2><span class="muted">Se cargan una sola vez, en orden, sobre una base vacía.</span></div>
    <div class="row">${pasos.map(p=>`<div class="note" style="flex:1 1 220px;display:flex;flex-direction:column;gap:8px"><b>${p[1]}</b><span>${p[2]}</span>
      ${ds[p[0]] ? pill('Cargado') : `<button class="btn ${p===prox?'p':''}" data-a="datosPrueba" data-paso="${p[0]}" ${p===prox?'':'disabled'}>Cargar</button>`}</div>`).join('')}</div></section>` : '';
  const semana = d.ventas_semana || [], mx = Math.max(1, ...semana.map(x=>x.total));
  const dias = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
  const medios = MEDIOS.map(([k,l])=>({l, v:(d.cobros_hoy||{})[k]||0, t:$$((d.cobros_hoy||{})[k]||0)}));
  const enMin = d.en_minimo || [], tr = d.remitos_en_transito || [];
  return cabecera('Inicio', `Resumen del ${new Date().toLocaleDateString('es-AR',{weekday:'long', day:'numeric', month:'long', year:'numeric'})}`, `<button class="btn p" data-a="go" data-v="ventas">Nueva venta</button>`) + prueba + `
  <section class="kpis">
    <div class="kpi"><div class="l">Cobrado hoy</div><div class="v">${$$(d.cobrado_hoy)}</div><div><span class="pill ok">${num(d.ventas_hoy)} ${d.ventas_hoy===1?'venta confirmada':'ventas confirmadas'}</span></div></div>
    <div class="kpi"><div class="l">Stock valorizado al costo</div><div class="v">${$$(d.stock_valorizado)}</div><div><span class="pill n">disponible + pendiente</span></div></div>
    <div class="kpi"><div class="l">Remitos en tránsito</div><div class="v">${tr.length}</div><div><span class="pill n">${tr.length ? 'por recibir en '+[...new Set(tr.map(nomUbi))].map(n=>esc(n.replace('Sucursal ',''))).join(', ') : 'nada en camino'}</span></div></div>
    <div class="kpi"><div class="l">Productos en su mínimo</div><div class="v">${enMin.length}</div><div><span class="pill ${enMin.length?'warn':'ok'}">${num(d.necesidades_pendientes)} ${d.necesidades_pendientes===1?'necesidad pendiente':'necesidades pendientes'}</span></div></div>
  </section>
  <section class="row">
    <div class="card grow2"><div class="head"><h2>Cobrado en los últimos 7 días</h2><span class="muted">Todas las sucursales, con recargos</span></div>
      <div class="vbars" role="img" aria-label="Total cobrado por día en la última semana">${semana.map((x,i)=>`<div class="${i===semana.length-1?'hoy':''}"><span>${x.total?(x.total>=1000?Math.round(x.total/1000)+' mil':$$(x.total)):'0'}</span><i style="height:${Math.round(x.total/mx*78)}%"></i></div>`).join('')}</div>
      <div class="vlab" aria-hidden="true">${semana.map(x=>{ const f = aFecha(x.dia); return `<span>${dias[f.getDay()]} ${f.getDate()}</span>`; }).join('')}</div></div>
    <div class="card grow1"><h2>Cobros de hoy por medio de pago</h2>${hbars(medios)}
      <div class="sum" style="border-top:1px solid var(--line);padding-top:12px"><span class="muted">Total del día</span><b>${$$(d.cobrado_hoy)}</b></div></div>
  </section>
  <section class="row">
    <div class="card grow1"><div class="head"><h2>Productos en su stock mínimo</h2><button class="btn s" data-a="go" data-v="inventario">Ver stock</button></div>
      ${enMin.slice(0,5).map(a=>`<div class="note warn"><b>${esc(nomProd(a.producto_id))}</b> en ${esc(nomUbi(a.ubicacion_id))} · disponible ${num(a.disponible)}, mínimo ${num(a.minimo)}</div>`).join('') || '<div class="note ok">Ningún producto está en su mínimo.</div>'}
      ${enMin.length>5?`<div class="muted">Y ${enMin.length-5} más.</div>`:''}</div>
    <div class="card grow1"><div class="head"><h2>Reposición en curso</h2><button class="btn s" data-a="go" data-v="logistica">Ver logística</button></div>
      <div>${[[d.necesidades_pendientes,'Necesidades pendientes','Pedidos de los locales sin consolidar'],[d.ordenes_por_preparar,'Órdenes por preparar','El CD arma y precinta los bultos'],[d.bultos_en_transito,'Bultos en tránsito','Despachados desde el CD'],[tr.length,'Remitos por recibir','El local controla cada precinto']]
        .map(f=>`<div class="item" style="justify-content:flex-start"><div class="step">${num(f[0])}</div><div><b>${f[1]}</b><div class="muted">${f[2]}</div></div></div>`).join('')}</div></div>
  </section>
  <section class="card"><div class="head"><h2>Últimas ventas</h2><button class="btn s" data-a="go" data-v="reportes">Ver reportes</button></div>
    ${tabla([['Fecha'],['Sucursal'],['Comprobante'],['Cliente'],['Medio de pago'],['Total','r']], (d.ultimas_ventas||[]).map(v=>`<tr><td>${fh(v.fecha_hora)}</td><td>${esc(v.sucursal)}</td><td>${esc(({TICKET:'Ticket',FACTURA_A:'Factura A',FACTURA_B:'Factura B'})[v.tipo]||v.tipo)} ${p2(v.punto_venta).padStart(4,'0')}-${String(v.numero).padStart(8,'0')}</td><td>${esc(v.cliente||'Consumidor final')}</td><td>${esc((v.medios||'').replace(/EFECTIVO|DEBITO|CREDITO|TRANSFERENCIA/g, nomMedio))}</td><td class="r"><b>${$$(v.total)}</b></td></tr>`))}</section>`;
}

function vAdministracion(){
  return cabecera('Administración', 'Altas, bajas y modificaciones de los datos base del comercio', btnAlta(ui.tab.administracion)) + tabs('administracion', [['ubicaciones','Sucursales y CD'],['categorias','Categorías'],['productos','Productos y precios'],['proveedores','Proveedores']]) + abmView(ui.tab.administracion);
}

function vInventario(){
  const t = ui.tab.inventario, d = ui.d; let cuerpo = '';
  if (!d) cuerpo = '<section class="card"><div class="vacio">No se pudieron cargar los datos.</div></section>';
  else if (t==='stock') { const u = ubicStock(), filasSt = d.filas || [];
    const tot = k => filasSt.reduce((a,f)=>a+f[k],0);
    const filas = filasSt.filter(f=>{ const p = prod(f.producto_id); return coincide(F('inv','q'), p.nombre, p.sku) && (!F('inv','cat')||String(p.categoria_id)===F('inv','cat')) && (!F('inv','estado')||estadoStock(f.disponible,f.minimo)===F('inv','estado')); });
    const ms = d.movimientos.filter(m=>!ui.movSku || m.producto_id===ui.movSku);
    cuerpo = `<section class="kpis">
      <div class="kpi"><div class="l"><span class="dot" style="background:var(--ok-dot)"></span>Disponible</div><div class="v">${num(tot('disponible'))} u.</div><div class="muted">Verificado. Es lo único que se puede vender.</div></div>
      <div class="kpi"><div class="l"><span class="dot" style="background:var(--warn-dot)"></span>Pendiente</div><div class="v">${num(tot('pendiente'))} u.</div><div class="muted">Viene en camino o llegó sin verificar el precinto.</div></div>
      <div class="kpi"><div class="l"><span class="dot" style="background:var(--bad-dot)"></span>Merma</div><div class="v">${num(tot('merma'))} u.</div><div class="muted">Bultos rechazados por precinto roto o distinto.</div></div></section>
    <section class="row"><div class="card grow2"><h2>Stock en ${esc(nomUbi(u))}</h2>
      <div class="bar">${fTxt('inv','q','Buscar producto por nombre o SKU')}${fSel('inv','cat','Categoría',optCat())}${fSel('inv','estado','Estado',[['','Todos'],['Normal','Normal'],['En el mínimo','En el mínimo'],['Bajo el mínimo','Bajo el mínimo']])}</div>
      ${tabla([['Producto'],['Disponible','r'],['Pendiente','r'],['Merma','r'],['Mínimo','r'],['Respecto del mínimo'],['Estado']], filas.map(f=>{ const e = estadoStock(f.disponible, f.minimo), col = e==='Normal'?'var(--accent)':e==='En el mínimo'?'var(--warn-dot)':'var(--bad-dot)';
        return `<tr class="click ${ui.movSku===f.producto_id?'sel':''}" data-a="verMov" data-id="${f.producto_id}"><td><b style="font-weight:500">${esc(nomProd(f.producto_id))}</b></td><td class="r"><b>${num(f.disponible)}</b></td><td class="r">${num(f.pendiente)}</td><td class="r">${num(f.merma)}</td><td class="r">${num(f.minimo)}</td><td><div class="mini"><i style="width:${Math.min(100, f.minimo?Math.round(f.disponible/(f.minimo*2.5)*100):100)}%;background:${col}"></i></div></td><td>${pill(e)}</td></tr>`; }))}
      <div class="muted">Hacé clic en un producto para ver solo sus movimientos. El stock mínimo se edita en Administración → Productos.</div></div>
      <div class="grow1" style="display:flex;flex-direction:column;gap:16px;min-width:0">
        <div class="card"><h2>Alertas de stock mínimo</h2><div class="muted">Aparecen cuando una venta o un despacho deja un producto en su mínimo (patrón Observer).</div>
          ${d.alertas.map(a=>`<div class="note warn"><b>${esc(nomProd(a.producto_id))}</b> quedó con ${num(a.disponible)} (mínimo ${num(a.minimo)}) · ${fh(a.fecha)}<div style="margin-top:8px"><button class="btn s" data-a="descartar" data-id="${a.producto_id}">Descartar alerta</button></div></div>`).join('') || '<div class="note ok">Sin alertas en esta ubicación.</div>'}</div>
        <div class="card"><h2>${ui.movSku ? 'Movimientos de '+esc(nomProd(ui.movSku)) : 'Últimos movimientos'}</h2><div class="scroll" style="max-height:420px">${ms.slice(0,40).map(m=>`<div class="item"><div><b style="font-weight:500">${esc(m.tipo)}</b><div class="muted">${esc(nomProd(m.producto_id))} · ${esc(m.documento)} · ${fh(m.fecha)}</div></div><b>${m.cantidad>0?'+':''}${num(m.cantidad)}</b></div>`).join('') || '<div class="muted">Sin movimientos todavía.</div>'}</div>
          <div class="muted">Los movimientos no se pueden modificar ni borrar.</div></div></div></section>`; }
  else if (t==='compras') { const filas = d.filter(o=>coincide(F('com','q'), o.numero, nomProv(o.proveedor_id), ...o.items.map(i=>nomProd(i.producto_id))) && (!F('com','estado')||o.estado===F('com','estado')) && (!F('com','prov')||String(o.proveedor_id)===F('com','prov')));
    cuerpo = `<section class="card"><h2>Órdenes de compra a proveedores</h2>
      <div class="bar">${fTxt('com','q','Buscar por número, proveedor o producto')}${fSel('com','prov','Proveedor',[['','Todos'],...C.proveedores.map(p=>[p.id,p.razon_social])])}${fSel('com','estado','Estado',[['','Todos'],['PENDIENTE','Pendiente'],['RECIBIDA','Recibida'],['ANULADA','Anulada']])}</div>
      ${tabla([['N°','r'],['Fecha'],['Proveedor'],['Productos'],['Total','r'],['Estado'],['']], filas.map(o=>`<tr><td class="r"><b>${o.numero}</b></td><td>${fd(o.fecha)}</td><td>${esc(nomProv(o.proveedor_id))}</td><td>${itemsTxt(o.items)}</td><td class="r">${$$(o.total)}</td><td>${pill(o.estado_nombre)}</td><td class="r">${o.estado==='PENDIENTE'?`<div class="ctl" style="justify-content:flex-end;flex-wrap:nowrap"><button class="btn s p" data-a="recibirOC" data-id="${o.id}">Recibir en el CD</button><button class="btn s" data-a="anularOC" data-id="${o.id}">Anular</button></div>`:''}</td></tr>`))}
      <div class="muted">Al recibir una orden, la mercadería ingresa como disponible en el Centro de Distribución.</div></section>`; }
  else if (t==='necesidades') { const filas = d.filter(n=>(!F('nec','suc')||String(n.sucursal_id)===F('nec','suc')) && (!F('nec','estado')||n.estado===F('nec','estado')) && coincide(F('nec','q'), n.id, n.origen, ...n.items.map(i=>nomProd(i.producto_id))));
    cuerpo = `<section class="card"><div class="head"><h2>Necesidades de reposición</h2><button class="btn" data-a="consolidar">Consolidar todas las pendientes de la sucursal</button></div>
      <div class="bar">${fTxt('nec','q','Buscar por número, origen o producto')}${fSel('nec','suc','Sucursal',optSuc(true))}${fSel('nec','estado','Estado',[['','Todos'],['PENDIENTE','Pendiente'],['CONSOLIDADA','Consolidada'],['ANULADA','Anulada']])}</div>
      ${tabla([['N°','r'],['Fecha'],['Sucursal'],['Origen'],['Productos pedidos'],['Estado'],['']], filas.map(n=>`<tr><td class="r"><b>${n.id}</b></td><td>${fd(n.fecha)}</td><td>${esc(nomUbi(n.sucursal_id))}</td><td>${esc(n.origen)}</td><td>${itemsTxt(n.items)}</td><td>${pill(n.estado_nombre)}</td><td class="r">${n.estado==='PENDIENTE'?`<div class="ctl" style="justify-content:flex-end;flex-wrap:nowrap"><button class="btn s p" data-a="necOrden" data-id="${n.id}">Generar orden</button><button class="btn s" data-a="necAnular" data-id="${n.id}">Anular</button></div>`:''}</td></tr>`))}
      <div class="muted">«Generar orden» crea una orden de reposición solo con esa necesidad. Para juntar varias, elegí una sucursal en el filtro y usá «Consolidar todas las pendientes de la sucursal».</div></section>`; }
  else { const filas = d.filter(o=>(!F('ord','suc')||String(o.destino_id)===F('ord','suc')) && (!F('ord','estado')||o.estado===F('ord','estado')) && coincide(F('ord','q'), o.numero, ...o.items.map(i=>nomProd(i.producto_id))));
    const o = d.find(x=>x.id===ui.ordSel) || filas[0];
    cuerpo = `<section class="row"><div class="card grow2"><h2>Órdenes de reposición CD → sucursal</h2>
      <div class="bar">${fTxt('ord','q','Buscar por número o producto')}${fSel('ord','suc','Destino',optSuc(true))}${fSel('ord','estado','Estado',[['','Todos'],['PENDIENTE','Pendiente'],['EN_PREPARACION','En preparación'],['DESPACHADA','Despachada'],['CERRADA_COMPLETA','Cerrada completa'],['CERRADA_CON_FALTANTES','Cerrada con faltantes']])}</div>
      ${tabla([['N°','r'],['Fecha'],['Destino'],['Necesidades'],['Renglones','r'],['Estado'],['']], filas.map(x=>`<tr class="click ${o&&x.id===o.id?'sel':''}" data-a="ordVer" data-id="${x.id}"><td class="r"><b>${x.numero}</b></td><td>${fd(x.fecha)}</td><td>${esc(nomUbi(x.destino_id))}</td><td>${x.necesidades.length?'N° '+x.necesidades.join(', '):'—'}</td><td class="r">${x.items.length}</td><td>${pill(x.estado_nombre)}</td><td class="r">${x.estado==='PENDIENTE'?`<button class="btn s p" data-a="iniciar" data-id="${x.id}">Iniciar preparación</button>`:''}</td></tr>`))}
      <div class="muted">Pendiente → En preparación → Despachada → Cerrada completa o con faltantes.</div></div>
      <div class="card grow1"><h2>${o ? 'Detalle de la orden N° '+o.numero : 'Detalle'}</h2>${o ? `<div>${pill(o.estado_nombre)} <span class="muted">CD → ${esc(nomUbi(o.destino_id))}</span></div>` + tabla([['Producto'],['Pedido','r'],['Empaquetado','r'],['Recibido','r'],['Falta','r']], o.items.map(i=>`<tr><td>${esc(nomProd(i.producto_id))}</td><td class="r">${num(i.solicitada)}</td><td class="r">${num(i.preparada)}</td><td class="r">${num(i.recibida)}</td><td class="r"><b>${num(i.solicitada-i.recibida)}</b></td></tr>`)) : '<div class="muted">Todavía no hay órdenes.</div>'}</div></section>`; }
  const der = t==='stock' ? fSel('inv','ubic','Ubicación',optUbi(false), ubicStock(), true) : t==='compras' ? '<button class="btn p" data-a="modal" data-m="oc">Nueva orden de compra</button>' : t==='necesidades' ? '<button class="btn p" data-a="modal" data-m="nd">Nueva necesidad</button>' : '';
  return cabecera('Inventario', 'Stock de cada producto en cada ubicación, compras y reposición', der) + tabs('inventario', [['stock','Stock por ubicación'],['compras','Compras a proveedores'],['necesidades','Necesidades'],['ordenes','Órdenes de reposición']]) + cuerpo;
}

const bTxt = b => b.items.map(i=>`${num(i.cantidad)} × ${esc(nomProd(i.producto_id))}`).join(' · ');
function vLogistica(){
  const t = ui.tab.logistica, d = ui.d; let cuerpo = '';
  if (!d) cuerpo = '<section class="card"><div class="vacio">No se pudieron cargar los datos.</div></section>';
  else if (t==='armado') { const o = ordenArmado(), emitidos = d.remitos.filter(r=>r.estado==='EMITIDO');
    const pend = o ? o.items.filter(i=>i.solicitada-i.preparada>0) : [];
    cuerpo = (!o ? '<section class="card"><div class="note">No hay órdenes pendientes ni en preparación. Generalas desde Inventario → Necesidades.</div></section>' : `<section class="row">
      <div class="card grow2"><div class="head"><h2>Orden a empaquetar</h2>${fSel('arm','orden','Orden',d.ordenes.map(x=>[x.id, `N° ${x.numero} → ${nomUbi(x.destino_id)} (${x.estado_nombre})`]), o.id)}</div>
        ${tabla([['Producto'],['Pedido','r'],['Empaquetado','r'],['Pendiente','r'],['Disponible en CD','r']], o.items.map(i=>`<tr><td>${esc(nomProd(i.producto_id))}</td><td class="r">${num(i.solicitada)}</td><td class="r">${num(i.preparada)}</td><td class="r"><b>${num(i.solicitada-i.preparada)}</b></td><td class="r">${num(o.disponible_cd[i.producto_id])}</td></tr>`))}
        <div class="muted">Al armar el primer bulto, una orden pendiente pasa a «En preparación».</div></div>
      <div class="card grow1"><h2>Armar nuevo bulto</h2>
        <div class="ctl" style="align-items:flex-end"><div class="f" style="flex:2 1 170px"><label for="arm-sku">Producto pendiente</label><select class="in" id="arm-sku">${opts(pend.map(i=>[i.producto_id, `${nomProd(i.producto_id)} (pend. ${i.solicitada-i.preparada})`]), '')}</select></div>
          <div class="f" style="flex:1 1 80px"><label for="arm-cant">Cantidad</label><input class="in" id="arm-cant" type="number" min="1" value="1"></div></div>
        <div class="ctl"><button class="btn" data-a="armAdd" style="flex:1 1 120px">Agregar al bulto</button><button class="btn" data-a="armTodo" style="flex:1 1 120px">Cargar todo lo pendiente</button></div>
        ${ui.arm.map((i,k)=>`<div class="sum"><span>${num(i.cantidad)} × ${esc(nomProd(i.producto_id))}</span><button class="btn s" data-a="armQuitar" data-i="${k}">Quitar</button></div>`).join('') || '<div class="muted">El bulto todavía está vacío.</div>'}
        <div class="f"><label for="arm-prec">N° de precinto (opcional)</label><input class="in" id="arm-prec" placeholder="Por ejemplo PREC-5001"></div>
        <button class="btn p" data-a="armConfirmar">Confirmar armado de bulto</button><div class="muted">Si informás el precinto ahora, el bulto queda directamente «Precintado».</div></div></section>`) +
      emitidos.map(r=>{ const listo = r.bultos.length && r.bultos.every(b=>b.estado==='PRECINTADO'); return `<section class="card"><div class="head"><h2>Remito ${esc(r.numero)} → ${esc(nomUbi(r.destino_id))}</h2>${pill(r.estado_nombre)}</div>
        ${r.bultos.map(b=>`<div class="item" style="flex-wrap:wrap"><div style="flex:1 1 260px;min-width:0"><b>${esc(b.codigo)}</b> ${pill(b.estado_nombre)}<div class="muted">${bTxt(b)}</div></div>
          ${b.estado==='PREPARADO' ? `<div class="ctl"><input class="in" id="prec-${b.id}" aria-label="Número de precinto para ${esc(b.codigo)}" placeholder="N° de precinto" style="width:160px"><button class="btn" data-a="precintar" data-id="${b.id}">Colocar precinto</button></div>` : `<span class="muted">Precinto ${esc(b.precinto)}</span>`}</div>`).join('')}
        <div class="ctl" style="align-items:flex-end"><div class="f" style="flex:2 1 180px"><label for="tr-${r.id}">Transportista</label><input class="in" id="tr-${r.id}" placeholder="Por ejemplo Transportes Córdoba"></div>
          <div class="f" style="flex:1 1 120px"><label for="pa-${r.id}">Patente</label><input class="in" id="pa-${r.id}" placeholder="AB123CD"></div>
          <button class="btn p" data-a="despachar" data-id="${r.id}" ${listo?'':'disabled'}>Despachar remito</button></div>
        <div class="muted">El remito se despacha cuando todos sus bultos están precintados. Al despachar, el stock sale del CD y queda pendiente en la sucursal.</div></section>`; }).join(''); }
  else if (t==='recepcion') { const rems = d.remitos.filter(r=>(r.estado==='EN_TRANSITO' || (r.estado==='RECIBIDO' && r.recepcion && !r.recepcion.cerrada)) && (!F('rec','suc')||String(r.destino_id)===F('rec','suc')));
    const r = rems.find(x=>String(x.id)===F('rec','remito')) || rems[0];
    let det = '';
    if (r && r.estado==='EN_TRANSITO') det = `<div class="muted">Salió del CD el ${fh(r.salida)} · ${esc(r.transporte)}. Primero registrá la llegada; después se controla el precinto de cada bulto.</div>
      ${r.bultos.map(b=>`<div class="item"><div><b>${esc(b.codigo)}</b> ${pill(b.estado_nombre)}<div class="muted">${bTxt(b)}</div></div></div>`).join('')}
      <div class="ctl" style="align-items:flex-end"><div class="f" style="flex:2 1 200px"><label for="rp-${r.id}">Recibido por</label><input class="in" id="rp-${r.id}" placeholder="Nombre de quien recibe"></div><button class="btn p" data-a="recibir" data-id="${r.id}">Registrar llegada</button></div>`;
    else if (r) { const falta = r.bultos.some(b=>b.estado==='RECIBIDO');
      det = `<div class="muted">Llegó el ${fh(r.recepcion.llegada)} · recibió ${esc(r.recepcion.recibido_por)}. Si el precinto llega completo y coincide con el del remito, el bulto queda verificado; si llega roto, incompleto o con otro número, se rechaza.</div>
      ${r.bultos.map(b=>`<div class="note" style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between"><div style="flex:1 1 240px;min-width:0"><b>${esc(b.codigo)}</b> ${pill(b.estado_nombre)}<div>${bTxt(b)}</div><div class="muted">Precinto del remito: ${esc(b.precinto)}${b.control?` · leído: ${esc(b.control.precinto_leido)} (${b.control.integro?'completo':'roto o incompleto'})`:''}</div></div>
        ${b.estado==='RECIBIDO' ? `<div class="ctl"><input class="in" id="lei-${b.id}" aria-label="Precinto leído en ${esc(b.codigo)}" placeholder="Precinto leído" value="${esc(b.precinto)}" style="width:150px"><select class="in" id="est-${b.id}" aria-label="Estado del precinto de ${esc(b.codigo)}"><option value="ok">Completo</option><option value="roto">Roto o incompleto</option></select><input class="in" id="obs-${b.id}" placeholder="Observación (opcional)" style="width:180px"><button class="btn p" data-a="controlar" data-id="${b.id}" data-rec="${r.recepcion.id}">Controlar</button></div>` : `<button class="btn s" data-a="verBulto" data-id="${b.id}">Ver trazabilidad</button>`}</div>`).join('')}
      <div class="ctl"><button class="btn p" data-a="cerrarRecepcion" data-rec="${r.recepcion.id}" ${falta?'disabled':''}>Cerrar recepción</button><span class="muted">Al cerrar se actualiza el stock: lo verificado pasa a disponible y lo rechazado a merma.</span></div>`; }
    cuerpo = `<section class="card"><div class="bar">${fSel('rec','suc','Sucursal',optSuc(true))}${r?fSel('rec','remito','Remito a recibir',rems.map(x=>[x.id, `${x.numero} · ${nomUbi(x.destino_id)} (${x.estado_nombre})`]), r.id):''}</div>
      ${r ? det : '<div class="note">No hay remitos en tránsito para recibir con ese filtro. Despachá uno desde Armado y despacho.</div>'}</section>`; }
  else { const b = d.bultos.find(x=>x.id===ui.bulto) || d.bultos[0];
    const filas = d.bultos.filter(x=>coincide(F('tra','q'), x.codigo, x.numero_remito, x.precinto, ...x.items.map(i=>nomProd(i.producto_id))) && (!F('tra','estado')||x.estado===F('tra','estado')) && (!F('tra','suc')||String(x.destino_id)===F('tra','suc')));
    cuerpo = `<section class="row"><div class="card grow2"><h2>Bultos</h2>
      <div class="bar">${fTxt('tra','q','Buscar por bulto, remito, precinto o producto')}${fSel('tra','suc','Destino',optSuc(true))}${fSel('tra','estado','Estado',[['','Todos'],['PREPARADO','Preparado'],['PRECINTADO','Precintado'],['EN_TRANSITO','En tránsito'],['RECIBIDO','Recibido'],['VERIFICADO','Verificado'],['RECHAZADO','Rechazado']])}</div>
      ${tabla([['Bulto'],['Remito'],['Destino'],['Precinto'],['Contenido'],['Estado']], filas.map(x=>`<tr class="click ${b&&x.id===b.id?'sel':''}" data-a="verBulto" data-id="${x.id}"><td><b>${esc(x.codigo)}</b></td><td>${esc(x.numero_remito)}</td><td>${esc(nomUbi(x.destino_id))}</td><td>${esc(x.precinto||'—')}</td><td>${bTxt(x)}</td><td>${pill(x.estado_nombre)}</td></tr>`))}</div>
      <div class="card grow1">${b ? `<h2>Trazabilidad de ${esc(b.codigo)}</h2><div>${pill(b.estado_nombre)}<div class="muted">Remito ${esc(b.numero_remito)} → ${esc(nomUbi(b.destino_id))} · Precinto ${esc(b.precinto||'sin colocar')}${b.motivo?' · '+esc(b.motivo):''}</div></div>
      <div class="tl">${d.historial.map(h=>`<div><span class="d ${h.codigo==='VERIFICADO'?'ok':h.codigo==='RECHAZADO'?'bad':''}"></span><div><b>${esc(h.estado)}</b><div class="muted">${fh(h.fecha)} · ${esc(h.usuario)}${h.observacion?' · '+esc(h.observacion):''}</div></div></div>`).join('')}</div>
      <div class="muted">El historial de estados solo admite altas: no se puede modificar ni borrar.</div>` : '<h2>Trazabilidad</h2><div class="muted">Todavía no hay bultos.</div>'}</div></section>`; }
  return cabecera('Logística', 'Bultos con remito y precinto, despacho desde el CD y recepción en el local') + tabs('logistica', [['armado','Armado y despacho'],['recepcion','Recepción en sucursal'],['trazabilidad','Trazabilidad de bultos']]) + cuerpo;
}

function vVentas(){
  const t = ui.tab.ventas, suc = sucVenta(), d = ui.d || {}; let cuerpo;
  const der = t==='clientes' ? btnAlta('clientes') : fSel('ven','suc','Sucursal',optSuc(false), suc, true);
  if (!suc && t!=='clientes') cuerpo = '<section class="card"><div class="note">No hay sucursales activas. Cargalas en Administración.</div></section>';
  else if (t==='nueva') { const sub = subtotal(), resta = Math.round((sub - pagado())*100)/100, cli = IDX.clientes[F('ven','cli')], disp = d.disponible || {};
    const comp = !cli || cli.condicion_iva==='CONSUMIDOR_FINAL' ? 'Ticket' : cli.condicion_iva==='RESPONSABLE_INSCRIPTO' ? 'Factura A' : 'Factura B';
    const lista = activos().filter(p=>coincide(F('ven','q'), p.nombre, p.sku) && (!F('ven','cat')||String(p.categoria_id)===F('ven','cat')));
    const medio = F('ven','medio','EFECTIVO');
    cuerpo = (d.caja ? '' : '<div class="note warn" style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between"><span>La caja de esta sucursal está cerrada. Para vender, primero hay que abrirla.</span><button class="btn s" data-a="tab" data-g="ventas" data-k="caja">Ir a Caja</button></div>') + `<section class="row">
    <div class="grow2" style="display:flex;flex-direction:column;gap:16px;min-width:0">
      <div class="card"><h2>Productos</h2><div class="bar">${fTxt('ven','q','Buscar por nombre o SKU')}${fSel('ven','cat','Categoría',optCat())}</div>
        <div>${lista.slice(0,8).map(p=>`<div class="item"><div style="min-width:0"><b style="font-weight:500">${esc(p.nombre)}</b><div class="muted">${esc(p.sku)} · disponible ${num(disp[p.id]||0)}</div></div><div class="ctl" style="flex-wrap:nowrap"><b>${$$(p.precio)}</b><button class="btn s" data-a="agregar" data-id="${p.id}" ${(disp[p.id]||0)>0?'':'disabled'} aria-label="Agregar ${esc(p.nombre)}">Agregar</button></div></div>`).join('') || '<div class="muted">Ningún producto coincide.</div>'}</div>
        <div class="muted">${lista.length>8?`Se muestran 8 de ${lista.length}. Afiná la búsqueda para ver el resto.`:`${lista.length} producto(s).`}</div></div>
      <div class="card"><h2>Renglones de la venta</h2>${tabla([['Producto'],['Precio','r'],['Cantidad'],['Subtotal','r']], ui.cart.map(i=>{ const p = prod(i.producto_id); return `<tr><td><b style="font-weight:500">${esc(p.nombre)}</b></td><td class="r">${$$(p.precio)}</td><td><span class="qty"><button data-a="menos" data-id="${p.id}" aria-label="Quitar una unidad">−</button><b>${i.cantidad}</b><button data-a="agregar" data-id="${p.id}" aria-label="Sumar una unidad">+</button></span></td><td class="r"><b>${$$(p.precio*i.cantidad)}</b></td></tr>`; }))}
        <div class="muted">Solo se puede vender el stock disponible y verificado de la sucursal.</div></div></div>
    <div class="card grow1"><h2>Cobro</h2>
      <div class="ctl"><div class="f"><label for="f-ven-vendedor">Vendedor</label><input class="in" id="f-ven-vendedor" data-f="ven.vendedor" value="${esc(F('ven','vendedor'))}" placeholder="Nombre"></div>
        <div class="f" style="flex:2 1 200px"><label for="f-ven-cli">Cliente</label><select class="in" id="f-ven-cli" data-f="ven.cli">${opts([['','Consumidor final (sin identificar)'],...C.clientes.map(c=>[c.id, `${c.nombre} · ${nomIva(c.condicion_iva)}`])], F('ven','cli'))}</select></div></div>
      <div class="note">Comprobante a emitir: <b>${comp}</b></div>
      <div class="sum"><span>Mercadería</span><b>${$$(sub)}</b></div>
      ${ui.pagos.map((p,i)=>`<div class="sum"><span>${nomMedio(p.medio)}${p.cuotas>1?` en ${p.cuotas} cuotas (recargo ${$$(recargo(p))})`:''}</span><span>${$$(p.monto)} <button class="btn s" data-a="quitarPago" data-i="${i}">Quitar</button></span></div>`).join('')}
      <div class="sum"><span class="muted">Falta cobrar</span><b style="color:${resta>0?'var(--warn-fg)':'var(--ok-fg)'}">${$$(resta)}</b></div>
      <div class="ctl"><div class="f"><label for="p-medio">Medio de pago</label><select class="in" id="p-medio" data-f="ven.medio">${opts(MEDIOS, medio)}</select></div>
        <div class="f"><label for="p-monto">Importe</label><input class="in" id="p-monto" type="number" min="0" step="0.01" value="${resta>0?resta:''}"></div>
        ${medio==='CREDITO'?`<div class="f"><label for="p-cuotas">Cuotas</label><select class="in" id="p-cuotas">${opts([1,3,6,12].map(c=>[String(c),String(c)]),'1')}</select></div>`:''}
</div>
      <button class="btn" data-a="pago" ${resta>0?'':'disabled'}>Agregar pago</button>
      <div class="sum" style="border-top:1px solid var(--line);padding-top:12px"><span>Total a cobrar</span><span class="big">${$$(sub + ui.pagos.reduce((a,p)=>a+recargo(p),0))}</span></div>
      <button class="btn p" data-a="confirmar">Confirmar venta</button>
      <div class="muted">Se puede cobrar con varios medios (patrón Strategy). El crédito suma 3 % por cada cuota después de la primera.</div></div></section>`; }
  else if (t==='devoluciones') { const ventas = (d.ventas||[]).filter(x=>coincide(F('dev','q'), x.comprobante, x.cliente) && (!F('dev','fecha')||(x.fecha||'').slice(0,10)===F('dev','fecha')));
    const v = (d.ventas||[]).find(x=>x.id===ui.devVenta);
    cuerpo = `<section class="row"><div class="card grow2"><h2>Ventas de ${esc(nomUbi(suc))} (últimos 30 días)</h2>
      <div class="bar">${fTxt('dev','q','Buscar por comprobante o cliente')}<div class="fs"><label class="lab" for="f-dev-fecha">Fecha</label><input class="in" type="date" id="f-dev-fecha" data-f="dev.fecha" value="${F('dev','fecha')}"></div></div>
      ${tabla([['Fecha'],['Comprobante'],['Cliente'],['Total','r'],['']], ventas.slice(0,15).map(x=>`<tr class="${x.id===ui.devVenta?'sel':''}"><td>${fh(x.fecha)}</td><td>${esc(x.comprobante)}</td><td>${esc(x.cliente)}</td><td class="r"><b>${$$(x.total)}</b></td><td class="r"><button class="btn s" data-a="devElegir" data-id="${x.id}">Elegir</button></td></tr>`))}
      <div class="muted">${ventas.length>15?`Se muestran 15 de ${ventas.length} ventas.`:`${ventas.length} venta(s).`} Solo se aceptan devoluciones de ventas registradas, dentro de los 30 días y sin superar lo vendido.</div></div>
      <div class="grow1" style="display:flex;flex-direction:column;gap:16px;min-width:0"><div class="card"><h2>Registrar devolución</h2>
        ${v ? `<div class="muted">${esc(v.comprobante)} · ${fh(v.fecha)}</div>` + tabla([['Producto'],['Vendidas','r'],['Devueltas','r'],['A devolver']], (d.renglones||[]).map(r=>`<tr><td>${esc(r.producto)}</td><td class="r">${r.cantidad}</td><td class="r">${r.devuelta}</td><td><input class="in" id="d-q${r.id}" type="number" min="0" max="${r.cantidad-r.devuelta}" value="0" aria-label="Unidades a devolver de ${esc(r.producto)}" style="width:80px"></td></tr>`)) +
          `<div class="f"><label for="d-motivo">Motivo</label><input class="in" id="d-motivo" placeholder="Por ejemplo: producto vencido"></div>
          <label class="ctl" style="min-height:44px"><input type="checkbox" id="d-reingresa" checked> El producto vuelve en buen estado y reingresa al stock</label>
          <button class="btn p" data-a="devolver">Registrar devolución</button><div class="muted">El reintegro sale de la caja abierta de la sucursal.</div>` : '<div class="note">Elegí una venta de la lista.</div>'}</div>
        <div class="card"><h2>Devoluciones registradas</h2>${(d.devs||[]).map(x=>`<div class="item"><div><b style="font-weight:500">${esc(x.nota)}</b><div class="muted">${esc(x.venta)} · ${esc(x.motivo)} · ${fh(x.fecha)}</div></div><b>${$$(x.total)}</b></div>`).join('') || '<div class="muted">Todavía no hay devoluciones.</div>'}</div></div></section>`; }
  else if (t==='caja') { const c = d.caja; const ms = c ? c.movimientos.filter(m=>(!F('caj','tipo')||m.tipo===F('caj','tipo')) && coincide(F('caj','q'), m.concepto, nomMedio(m.medio_pago))) : [];
    cuerpo = `<section class="row"><div class="card grow1"><h2>Caja de ${esc(nomUbi(suc))}</h2><div>${pill(c?'Abierta':'Cerrada')}</div>
      ${c ? `<div class="muted">Abierta el ${fh(c.fecha_apertura)}</div><div class="sum"><span>Saldo inicial</span><b>${$$(c.saldo_inicial)}</b></div><div class="sum"><span>Movimientos</span><b>${$$(c.saldo-c.saldo_inicial)}</b></div>
        <div class="sum" style="border-top:1px solid var(--line);padding-top:12px"><span>Saldo actual</span><span class="big">${$$(c.saldo)}</span></div><button class="btn" data-a="cerrarCaja">Cerrar caja</button>`
        : `<div class="f"><label for="c-inicial">Saldo inicial</label><input class="in" id="c-inicial" type="number" min="0" value="50000"></div><button class="btn p" data-a="abrirCaja">Abrir caja</button>`}
      <div class="muted">Cada sucursal tiene una sola caja abierta a la vez. Sin caja abierta no se puede vender ni devolver.</div></div>
      <div class="card grow2"><h2>Movimientos de la caja abierta</h2><div class="bar">${fTxt('caj','q','Buscar por concepto o medio de pago')}${fSel('caj','tipo','Tipo',[['','Todos'],['INGRESO','Ingresos'],['EGRESO','Egresos']])}</div>
        ${tabla([['Fecha'],['Tipo'],['Concepto'],['Medio'],['Importe','r']], ms.map(m=>`<tr><td>${fh(m.fecha_hora)}</td><td>${m.tipo==='INGRESO'?'Ingreso':'Egreso'}</td><td>${esc(m.concepto)}</td><td>${esc(nomMedio(m.medio_pago))}</td><td class="r"><b>${m.tipo==='EGRESO'?'-':''}${$$(m.monto)}</b></td></tr>`))}</div></section>`; }
  else cuerpo = abmView('clientes');
  return cabecera('Ventas', 'Ventas con uno o varios medios de pago, devoluciones, caja por sucursal y clientes', der) + tabs('ventas', [['nueva','Nueva venta'],['devoluciones','Devoluciones'],['caja','Caja'],['clientes','Clientes']]) + cuerpo;
}

const ES_NUM = /^(-?\$ )?-?[\d.,]+( %| u\.)?$|^—$/;
const REPS = [['r1','Existencias y stock mínimo','Qué hay en cada ubicación y qué está en su mínimo'],['r2','Productos más vendidos y margen','Unidades, ingresos y ganancia por producto'],['r3','Movimientos y valorización','Entradas, salidas y valor del inventario'],['r4','Tiempo de tránsito CD → locales','Horas entre el despacho y la recepción'],['r5','Bultos rechazados y mermas','Rechazos por precinto y su costo'],['r6','Ventas por período, local y medio de pago','Cuánto se vendió y cómo se cobró']];
const TIPOS_MOV = [['INGRESO_COMPRA','Compra a proveedor'],['EGRESO_DESPACHO','Despacho a sucursal'],['INGRESO_PENDIENTE','Ingreso pendiente de verificación'],['CONFIRMACION_VERIFICADO','Verificado (pasa a disponible)'],['MERMA_RECHAZO','Merma por rechazo'],['EGRESO_VENTA','Venta'],['REINGRESO_DEVOLUCION','Devolución de cliente']];
const ANOMALIAS = [['PRECINTO_ROTO','Precinto roto'],['PRECINTO_NO_COINCIDE','Precinto no coincide'],['ROTO_Y_NO_COINCIDE','Roto y no coincide']];
const FILTROS_REP = { r1:['ubicacion','categoria','solo_minimo'], r2:['desde','hasta','sucursal','categoria'], r3:['desde','hasta','ubicacion','categoria','tipo'], r4:['desde','hasta','sucursal'], r5:['desde','hasta','sucursal','categoria','anomalia'], r6:['desde','hasta','sucursal','medio'] };
const DEF_REP = { desde: () => iso(haceDias(30)), hasta: () => iso(new Date()) };
function consultaReporte(){ return FILTROS_REP[ui.rep].map(k=>[k, F('rep', k, DEF_REP[k] ? DEF_REP[k]() : '')]).filter(([,v])=>v).map(([k,v])=>`${k}=${encodeURIComponent(v)}`).join('&'); }
function filtroRep(k){
  if (k==='desde' || k==='hasta') return fDate('rep', k, k==='desde'?'Desde':'Hasta', DEF_REP[k]());
  const sel = (label, items) => fSel('rep', k, label, items, '', true);
  return { ubicacion: sel('Ubicación', optUbi(true)), sucursal: sel('Sucursal', optSuc(true)), categoria: sel('Categoría', optCat()),
    solo_minimo: sel('Mostrar', [['','Todos los productos'],['1','Solo en stock mínimo']]), tipo: sel('Tipo', [['','Todos'],...TIPOS_MOV]),
    anomalia: sel('Anomalía', [['','Todas'],...ANOMALIAS]), medio: sel('Medio de pago', [['','Todos'],...MEDIOS]) }[k];
}
function vReportes(){
  const k = ui.rep, d = ui.d, q = consultaReporte();
  const g = d && d.grafico;
  const cuerpo = !d ? '<div class="card"><div class="vacio">No se pudo cargar el reporte.</div></div>' : `
      <div class="card"><div class="head"><h2>${esc(d.titulo)}</h2><div class="ctl"><a class="btn" href="/api/reportes/${k}/exportar?formato=pdf&${q}">Exportar a PDF</a><a class="btn" href="/api/reportes/${k}/exportar?formato=csv&${q}">Exportar a CSV</a></div></div>
        <div class="bar" style="align-items:flex-end">${FILTROS_REP[k].map(filtroRep).join('')}</div>
        <div class="kpis">${d.resumen.map(r=>`<div class="kpi" style="background:var(--surface2);flex-basis:150px"><div class="l">${esc(r[0])}</div><div class="v" style="font-size:20px">${esc(r[1])}</div></div>`).join('')}</div></div>
      ${g ? `<div class="card"><h2>${esc(g.titulo)}</h2>${hbars(g.etiquetas.map((l,i)=>({l, v:g.valores[i], t:num(g.valores[i]), alerta:(g.alertas||[])[i]})))}</div>` : ''}
      ${d.secciones.map(s=>{ const nums = s.columnas.map((c,i)=>s.filas.length>0 && s.filas.every(f=>ES_NUM.test(f[i])));
        return `<div class="card"><div class="head"><h2>${esc(s.titulo)}</h2><span class="muted">${s.filas.length} fila(s)</span></div><div class="scroll">${tabla(s.columnas.map((c,i)=>[esc(c), nums[i]?'r':'']), s.filas.map(f=>`<tr>${f.map((c,i)=>`<td class="${nums[i]?'r':''}">${esc(c)}</td>`).join('')}</tr>`))}</div></div>`; }).join('')}`;
  return cabecera('Reportes', 'Seis reportes con filtros, totales y gráfico, exportables a PDF y CSV') + `<section class="row">
    <div class="rep grow1" style="flex:0 1 300px">${REPS.map(r=>`<button class="${r[0]===k?'on':''}" data-a="rep" data-k="${r[0]}" aria-pressed="${r[0]===k}"><b>${r[1]}</b><small>${r[2]}</small></button>`).join('')}</div>
    <div class="grow2" style="display:flex;flex-direction:column;gap:16px;min-width:0">${cuerpo}</div></section>`;
}

// ---------- arranque ----------
const V = {inicio:vInicio, administracion:vAdministracion, inventario:vInventario, logistica:vLogistica, ventas:vVentas, reportes:vReportes};
function render(keep){
  const view = document.getElementById('view'); let foco = null; const vals = {};
  if (keep) { const a = document.activeElement; if (a && a.id) { let s = null; try { s = a.selectionStart; } catch (e) {} foco = {id:a.id, s}; }
    view.querySelectorAll('input[id],select[id]').forEach(el => { if (!el.dataset.f) vals[el.id] = el.type==='checkbox' ? el.checked : el.value; }); }
  document.getElementById('nav').innerHTML = VISTAS.map(([k,l,d])=>`<a href="#${k}" class="${ui.view===k?'on':''}" ${ui.view===k?'aria-current="page"':''}><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"></path></svg><span>${l}</span></a>`).join('');
  view.innerHTML = V[ui.view]() + modal();
  if (keep) { for (const id in vals) { const el = document.getElementById(id); if (el) { if (el.type==='checkbox') el.checked = vals[id]; else el.value = vals[id]; } }
    if (foco) { const el = document.getElementById(foco.id); if (el) { el.focus(); try { if (foco.s != null) el.setSelectionRange(foco.s, foco.s); } catch (e) {} } } }
}
async function ruta(){ const h = location.hash.slice(1); ui.view = V[h] ? h : 'inicio'; ui.modal = null; ui.d = null; await refrescar(); window.scrollTo(0,0); }
async function filtro(e){ const k = e.target.dataset && e.target.dataset.f; if (!k) return; const [g,c] = k.split('.'); (ui.f[g] ||= {})[c] = e.target.value; if (ON[k]) ON[k]();
  if (e.target.dataset.fr) await refrescar(); else render(true); }
document.addEventListener('click', async e => {
  const el = e.target.closest('[data-a]'); if (!el || el.disabled || ui.ocupado) return;
  if (el.tagName==='TR' && e.target.closest('button')) return;
  const f = A[el.dataset.a]; if (!f) return;
  ui.ocupado = true; document.body.classList.add('ocupado');
  try { const r = await f(el.dataset); if (r !== 'HECHO') render(r==='ERR'); }
  finally { ui.ocupado = false; document.body.classList.remove('ocupado'); }
});
document.addEventListener('input', e => { if (e.target.tagName==='INPUT' && e.target.type!=='date') filtro(e); });
document.addEventListener('change', e => { if (e.target.tagName==='SELECT' || e.target.type==='date') filtro(e); });
window.addEventListener('hashchange', ruta);
(async () => { try { await cargarCatalogo(); } catch (e) { err('No se pudo conectar con el servidor: ' + e.message); } await ruta(); })();
