"use strict";
// The standalone HTML stores data in IndexedDB; the Python app uses the same UI with SQLite.
window.LocalLibrary = (() => {
  const fields = ["name","description","category","status","tags","repo_url","demo_url","local_path","notes","favorite","url","cover_url"];
  const statuses = ["计划中","进行中","已完成","已归档"];
  const colors = ["violet","blue","green","orange","rose","slate"];
  function url(value) {
    if (typeof value !== "string" || !value.trim() || value.length > 2048 || /[\s\x00-\x1f\\]/.test(value.trim())) throw new Error("请输入有效的网址，网址中不能有空格或换行。");
    value = value.trim();
    if (!/^[a-z][a-z\d+.-]*:/i.test(value)) value = "https://" + value;
    let parsed;
    try { parsed = new URL(value); } catch { throw new Error("请输入有效的 http 或 https 网址。"); }
    if (!["http:","https:"].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) throw new Error("网址必须是 http 或 https 地址，且不能包含账号密码。");
    return parsed.href;
  }
  function key(value) {
    if (!value) return "";
    const parsed = new URL(url(value)); parsed.hash = "";
    parsed.pathname = parsed.pathname.replace(/\/+$/, "");
    if (parsed.hostname === "github.com") parsed.pathname = parsed.pathname.toLowerCase().replace(/\.git$/, "");
    return parsed.href.replace(/\/$/, "");
  }
  function validate(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("项目格式无效。");
    const result = {};
    const limits = {name:120,description:2000,category:80,status:20,repo_url:2048,demo_url:2048,local_path:2048,notes:20000,url:2048,cover_url:700000};
    for (const [field,limit] of Object.entries(limits)) {
      const value=raw[field] ?? "";
      if(typeof value!=="string" || value.length>limit) throw new Error("项目字段格式错误或内容过长。");
      result[field]=value.trim();
    }
    if (!result.name) throw new Error("请填写卡片标题。");
    result.category ||= "未分类"; result.status ||= "计划中";
    if (!statuses.includes(result.status)) throw new Error("项目状态无效。");
    for (const field of ["url","repo_url","demo_url"]) if(result[field]) result[field]=url(result[field]);
    const cover=result.cover_url;
    if(cover.startsWith("data:")) {
      const match=cover.match(/^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$/);
      let valid=false;
      try {
        const bytes=atob(match?.[2] || "");
        valid=(match?.[1]==="png" && bytes.startsWith("\x89PNG\r\n\x1a\n")) || (match?.[1]==="jpeg" && bytes.startsWith("\xff\xd8\xff")) || (match?.[1]==="webp" && bytes.startsWith("RIFF") && bytes.slice(8,12)==="WEBP");
      } catch {}
      if(!valid) throw new Error("封面只支持 PNG、JPEG 或 WebP 图片。");
    } else if(cover) result.cover_url=url(cover);
    if(!Array.isArray(raw.tags ?? []) || (raw.tags ?? []).length>30 || (raw.tags ?? []).some(t=>typeof t!=="string" || t.length>60)) throw new Error("标签最多 30 个，每个最多 60 个字符。");
    result.tags=[...new Set((raw.tags || []).map(t=>t.trim()).filter(Boolean))];
    if(raw.favorite!==undefined && typeof raw.favorite!=="boolean") throw new Error("收藏标记无效。");
    result.favorite=raw.favorite || false;
    return result;
  }
  function category(raw) {
    if(!raw || typeof raw.name!=="string" || !raw.name.trim() || raw.name.trim().length>80 || !colors.includes(raw.color || "violet")) throw new Error("分类名称或颜色无效。");
    return {name:raw.name.trim(),color:raw.color || "violet"};
  }
  function ensureCategory(state,name) {
    if(!state.categories.some(c=>c.name===name)) state.categories.push({name,color:name==="未分类"?"slate":"violet"});
  }
  function initialState() {
    const seed=window.LOCAL_SEED || {projects:[],categories:[]};
    const state={projects:[],categories:(seed.categories || []).map(category),nextId:1};
    ensureCategory(state,"未分类");
    for(const raw of seed.projects || []) {
      const project=validate(raw), timestamp=new Date().toISOString();
      state.projects.push({...project,id:state.nextId++,created_at:raw.created_at || timestamp,updated_at:raw.updated_at || timestamp});
      ensureCategory(state,project.category);
    }
    return state;
  }
  let connection;
  function database() {
    if(!connection) connection=new Promise((resolve,reject)=>{
      let request;
      try { request=indexedDB.open("shizuo-project-collection",1); }
      catch { reject(new Error("浏览器不允许本地保存。请用正常模式的 Chrome、Edge 或 Firefox 打开，不要使用隐私模式。")); return; }
      request.onupgradeneeded=()=>request.result.createObjectStore("library");
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(new Error("无法打开浏览器本地存储，请尝试 Chrome 或 Edge 的正常窗口。"));
      request.onblocked=()=>reject(new Error("请关闭其他项目库窗口后重试。"));
    });
    return connection;
  }
  async function transaction(write,action) {
    const db=await database();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction("library",write?"readwrite":"readonly"), store=tx.objectStore("library");
      let result, failed=false;
      tx.oncomplete=()=>resolve(result);
      tx.onabort=tx.onerror=()=>{if(!failed)reject(new Error("本地保存失败，可能是存储空间不足。请先导出备份并检查浏览器设置。"));};
      const request=store.get("main");
      request.onsuccess=()=>{
        try {
          const state=request.result || initialState();
          result=action(state);
          if(write)store.put(state,"main");
        } catch(error) { failed=true;tx.abort();reject(error); }
      };
    });
  }
  function duplicate(state,project,exclude) {
    if(!project.url)return;
    const target=key(project.url);
    if(state.projects.some(p=>p.id!==exclude && [p.url,p.repo_url,p.demo_url].filter(Boolean).some(u=>key(u)===target))) throw new Error("这个网址已经收藏过了，可以直接编辑已有卡片。");
  }
  function insert(state,raw,dates={}) {
    const project=validate(raw), timestamp=new Date().toISOString();
    const saved={...project,id:state.nextId++,created_at:dates.created_at || timestamp,updated_at:dates.updated_at || timestamp};
    state.projects.push(saved);ensureCategory(state,saved.category);return saved;
  }
  function preview(value) {
    const normalized=url(value), domain=new URL(normalized).hostname.replace(/^www\./,"");
    return {url:normalized,name:domain.slice(0,120),description:"",cover_url:"",metadata_loaded:false};
  }
  async function github(username) {
    if(!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(username)) throw new Error("请填写 GitHub 用户名。");
    const projects=[];
    try {
      for(let page=1;page<=10;page++) {
        const response=await fetch(`https://api.github.com/users/${encodeURIComponent(username)}/repos?per_page=100&sort=updated&page=${page}`,{signal:AbortSignal.timeout(12000),credentials:"omit"});
        if(!response.ok)throw new Error();
        const rows=await response.json();
        if(!Array.isArray(rows))throw new Error();
        for(const repo of rows)projects.push(validate({name:repo.name,description:repo.description || "",category:"GitHub 项目",status:repo.archived?"已归档":"计划中",tags:[...new Set([repo.language,...(repo.topics || [])].filter(Boolean))].slice(0,30),repo_url:repo.html_url,url:repo.html_url,demo_url:/^https?:\/\//.test(repo.homepage || "")?repo.homepage:"",notes:"从 GitHub 导入，请按实际进度调整状态。"}));
        if(rows.length<100)return {projects,truncated:false,source:"api"};
      }
      return {projects,truncated:true,source:"api"};
    }catch {throw new Error("暂时无法读取 GitHub，请检查网络或稍后重试。你仍可以直接粘贴仓库网址生成卡片。");}
  }
  async function api(path,method="GET",body) {
    const parsed=new URL(path,"http://local.library"), pathname=parsed.pathname;
    if(pathname==="/api/github")return github(parsed.searchParams.get("username"));
    if(pathname==="/api/preview")return preview(body?.url);
    const read=method==="GET" && pathname!=="/api/bootstrap";
    return transaction(!read,state=>{
      if(method==="GET" && ["/api/bootstrap","/api/projects"].includes(pathname))return {token:"local",projects:state.projects,categories:state.categories};
      if(method==="GET" && pathname==="/api/export")return {format:"project-collection",version:2,exported_at:new Date().toISOString(),projects:state.projects,categories:state.categories};
      if(method==="POST" && pathname==="/api/links") {
        const data=preview(body?.url), normalized=data.url, githubLink=new URL(normalized).hostname==="github.com";
        const raw={...data,category:body.category || "未分类",repo_url:githubLink?normalized:"",demo_url:githubLink?"":normalized};
        duplicate(state,raw);
        return {project:insert(state,raw),metadata_loaded:false};
      }
      if(method==="POST" && pathname==="/api/projects") {
        const project=validate(body);duplicate(state,project);return insert(state,project);
      }
      const projectMatch=pathname.match(/^\/api\/projects\/(\d+)$/);
      if(projectMatch) {
        const id=Number(projectMatch[1]), index=state.projects.findIndex(p=>p.id===id);
        if(index<0)throw new Error("卡片不存在，可能已被删除。");
        if(method==="DELETE"){state.projects.splice(index,1);return {deleted:true};}
        if(method==="PUT"){
          const value=validate(body);duplicate(state,value,id);
          state.projects[index]={...value,id,created_at:state.projects[index].created_at,updated_at:new Date().toISOString()};
          ensureCategory(state,value.category);return state.projects[index];
        }
      }
      const categoryMatch=pathname.match(/^\/api\/categories\/(.+)$/);
      if(method==="POST" && pathname==="/api/categories") {
        const value=category(body);
        if(state.categories.some(c=>c.name===value.name))throw new Error("这个分类已经存在。");
        state.categories.push(value);return value;
      }
      if(categoryMatch) {
        const old=decodeURIComponent(categoryMatch[1]), index=state.categories.findIndex(c=>c.name===old);
        if(index<0)throw new Error("这个分类已不存在。");
        if(method==="DELETE"){
          if(old==="未分类")throw new Error("默认的未分类不能删除。");
          state.categories.splice(index,1);let moved=0;
          for(const p of state.projects)if(p.category===old){p.category="未分类";p.updated_at=new Date().toISOString();moved++;}
          return {moved};
        }
        if(method==="PUT"){
          const value=category(body);
          if(old==="未分类" && value.name!==old)throw new Error("未分类是默认分类，不能改名。");
          if(old!==value.name && state.categories.some(c=>c.name===value.name))throw new Error("这个分类名称已被使用。");
          state.categories[index]=value;
          if(old!==value.name)for(const p of state.projects)if(p.category===old){p.category=value.name;p.updated_at=new Date().toISOString();}
          return value;
        }
      }
      if(method==="POST" && pathname==="/api/import") {
        if(!body || body.format!=="project-collection" || ![1,2].includes(body.version) || !Array.isArray(body.projects) || body.projects.length>2000)throw new Error("请选择本工具导出的有效 JSON 备份。");
        if(body.categories!==undefined && (!Array.isArray(body.categories)||body.categories.length>500))throw new Error("备份中的分类列表无效。");
        const importedCategories=(body.categories || []).map(category);
        const rows=body.projects.map(raw=>{
          const project=validate(raw),dates={};
          for(const field of ["created_at","updated_at"])if(raw[field]!==undefined){
            if(typeof raw[field]!=="string" || !/(?:Z|[+-]\d{2}:\d{2})$/.test(raw[field]) || !Number.isFinite(Date.parse(raw[field])))throw new Error("备份中的项目时间格式无效，未导入任何记录。");
            dates[field]=new Date(raw[field]).toISOString();
          }
          return {project,dates};
        });
        const signature=p=>JSON.stringify(fields.map(f=>p[f]));
        const signatures=new Set(state.projects.map(signature));
        const urls=new Set(state.projects.flatMap(p=>[p.url,p.repo_url,p.demo_url].filter(Boolean).map(key)));
        for(const c of importedCategories)if(!state.categories.some(old=>old.name===c.name))state.categories.push(c);
        let added=0,skipped=0;
        for(const {project,dates} of rows){
          const keys=[project.url,project.repo_url,project.demo_url].filter(Boolean).map(key);
          if(keys.some(k=>urls.has(k)) || signatures.has(signature(project))){skipped++;continue;}
          insert(state,project,dates);keys.forEach(k=>urls.add(k));signatures.add(signature(project));added++;
        }
        return {added,skipped};
      }
      throw new Error("无法识别这个操作。");
    });
  }
  return {api,normalizeUrl:url};
})();
