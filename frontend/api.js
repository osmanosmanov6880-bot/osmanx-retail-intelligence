let token=sessionStorage.getItem('osmanx_admin_token')||'';
export const setToken=value=>{token=value||'';if(token)sessionStorage.setItem('osmanx_admin_token',token);else sessionStorage.removeItem('osmanx_admin_token')};
export const hasToken=()=>!!token;
export async function api(path,{method='GET',body,auth=false,kioskToken=null}={}){
  const headers={'Accept':'application/json'};
  if(body!==undefined)headers['Content-Type']='application/json';
  if(auth&&token)headers.Authorization=`Bearer ${token}`;
  if(kioskToken)headers['X-OSMANX-Kiosk']=kioskToken;
  let result;
  try {result=await fetch(`/api${path}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'})}
  catch{throw new Error('Нет соединения с сервером. Проверьте запуск приложения.')}
  const data=await result.json().catch(()=>({detail:`HTTP ${result.status}`}));
  if(!result.ok){if(result.status===401&&auth)setToken('');throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${result.status}`)}
  return data;
}


export async function downloadReport(path, filename){
  const headers={Accept:'text/csv'};
  if(token) headers.Authorization=`Bearer ${token}`;
  const res=await fetch(`/api${path}`,{headers,cache:'no-store'});
  if(!res.ok) throw new Error(`Не удалось получить отчёт: HTTP ${res.status}`);
  const blob=await res.blob();
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');
  anchor.href=url;anchor.download=filename;
  document.body.append(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),4000);
}
