let token=sessionStorage.getItem('osmanx_admin_token')||'';
export const setToken=value=>{token=value||'';if(token)sessionStorage.setItem('osmanx_admin_token',token);else sessionStorage.removeItem('osmanx_admin_token')};
export const hasToken=()=>!!token;
export async function api(path,{method='GET',body,auth=false}={}){
  const headers={'Accept':'application/json'};
  if(body!==undefined)headers['Content-Type']='application/json';
  if(auth&&token)headers.Authorization=`Bearer ${token}`;
  let result;
  try {result=await fetch(`/api${path}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'})}
  catch{throw new Error('Нет соединения с сервером. Проверьте запуск приложения.')}
  const data=await result.json().catch(()=>({detail:`HTTP ${result.status}`}));
  if(!result.ok){if(result.status===401&&auth)setToken('');throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${result.status}`)}
  return data;
}
