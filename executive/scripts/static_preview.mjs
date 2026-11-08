import {writeFileSync} from 'node:fs';
const root={innerHTML:'',addEventListener:()=>{},querySelector:()=>null};
globalThis.document={getElementById:()=>root,title:'',activeElement:null};
globalThis.window={scrollTo:()=>{}};
globalThis.localStorage={getItem:()=>null,setItem:()=>{}};
await import('../src/app.mjs');
const css='<link rel="stylesheet" href="../src/styles.css" /><link rel="stylesheet" href="../src/luxury.css" />';
const html=`<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8" />${css}<style>@page{size:1440px 1550px;margin:0}body{width:1440px;min-width:1440px}.topbar{position:relative}</style></head><body><div id="app">${root.innerHTML}</div></body></html>`;
writeFileSync(new URL('preview_dashboard.html',import.meta.url),html);
