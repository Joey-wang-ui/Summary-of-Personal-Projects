"use strict";
const $=selector=>document.querySelector(selector);
const standalone=location.protocol==="file:" || Boolean(window.FORCE_LOCAL_MODE);
let projects=[],categories=[],token="",view="all",activeCategory="",currentId=null,githubPreview=[],previewOwner="",toastTimer,lastAdded=null;
const viewNames={all:"全部作品",favorite:"我的收藏",github:"GitHub 项目"};
const statusClasses={"进行中":"status-progress","已完成":"status-done","已归档":"status-archived"};
const fields=["name","description","category","status","repo_url","demo_url","local_path","notes","url","cover_url"];
const paths={grid:["M3 3h7v7H3z","M14 3h7v7h-7z","M3 14h7v7H3z","M14 14h7v7h-7z"],star:["m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"],folder:["M3 7V5a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"],plus:["M12 5v14M5 12h14"],search:["M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15Z","m16 16 5 5"],link:["m10 13 4-4","M8 15H6a4 4 0 0 1-2.8-6.8l4-4A4 4 0 0 1 14 7","M16 9h2a4 4 0 0 1 2.8 6.8l-4 4A4 4 0 0 1 10 17"],external:["M14 3h7v7M21 3l-10 10","M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"],download:["M12 3v12m-5-5 5 5 5-5","M4 16v5h16v-5"],upload:["M12 16V4m-5 5 5-5 5 5","M4 16v5h16v-5"],close:["m6 6 12 12M6 18 18 6"],menu:["M4 6h16M4 12h16M4 18h16"],more:["M5 12h.01M12 12h.01M19 12h.01"],list:["M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01"],image:["M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z","m3 17 6-6 4 4 3-3 5 5","M16 7h.01"],layers:["m12 3 10 6-10 6L2 9Z","m2 14 10 6 10-6M2 19l10 6 10-6"],globe:["M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18","M12 3c5 6 5 12 0 18-5-6-5-12 0-18Z"],edit:["m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z"],info:["M12 8h.01M12 11v6","M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"],github:["M9 19c-4 1-4-2-6-2m12 5v-4c0-1-.3-1.7-1-2 3-.4 6-1.5 6-6a5 5 0 0 0-1.5-3.5 5 5 0 0 0-.1-3.5S17 2.5 14 4a14 14 0 0 0-5 0C6 2.5 4.6 3 4.6 3a5 5 0 0 0-.1 3.5A5 5 0 0 0 3 10c0 4.5 3 5.6 6 6-.7.3-1 1-1 2v4"]};
function icon(name){const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("aria-hidden","true");svg.classList.add("icon");for(const d of paths[name] || paths.folder){const p=document.createElementNS(svg.namespaceURI,"path");p.setAttribute("d",d);svg.append(p);}return svg;}
function el(tag,className,text){const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=text;return n;}
function buttonIcon(name,label,action,className="icon-button"){const b=el("button",className);b.type="button";b.append(icon(name));b.setAttribute("aria-label",label);b.title=label;b.addEventListener("click",action);return b;}
function notify(message){$("#toast").textContent=message;$("#toast").hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$("#toast").hidden=true;},5000);}
async function api(path,method="GET",data){
  if(standalone)return window.LocalLibrary.api(path,method,data);
  let response;try{response=await fetch(path,{method,headers:{"Content-Type":"application/json","X-Local-Token":token},...(data===undefined?{}:{body:JSON.stringify(data)})});}catch{throw new Error("无法连接本地服务。请重新运行启动文件，或双击“打开项目库.html”使用免安装版。");}
  const result=await response.json();if(!response.ok)throw new Error(result.error || "操作未完成，请重试。");return result;
}
async function refresh(){const result=await api("/api/projects");projects=result.projects;categories=result.categories;render();}
function primaryUrl(p){return p.url || p.demo_url || p.repo_url || "";}
function domain(p){try{return new URL(primaryUrl(p)).hostname.replace(/^www\./,"");}catch{return "本地项目记录";}}
function isGitHub(p){try{return new URL(p.repo_url || primaryUrl(p)).hostname==="github.com";}catch{return false;}}
function externalLink(url,label,className){const a=el("a",className,label);a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a;}
function categoryOptions(select,selected){select.replaceChildren(...categories.map(c=>new Option(c.name,c.name)));select.value=categories.some(c=>c.name===selected)?selected:"未分类";}
function closeSidebar(){$("#sidebar").classList.remove("is-open");$("#sidebar-shade").hidden=true;$("#sidebar-toggle").setAttribute("aria-expanded","false");}
function setView(next,category=""){view=next;activeCategory=category;$("#search").value="";$("#status-filter").value="";categoryOptions($("#quick-category"),category || $("#quick-category").value);render();closeSidebar();}
function openCategory(category){const form=$("#category-form");form.reset();form.elements.original.value=category?.name || "";form.elements.name.value=category?.name || "";form.elements.color.value=category?.color || "violet";form.elements.name.readOnly=category?.name==="未分类";$("#category-dialog-title").textContent=category?"管理分类":"新建分类";$("#delete-category").hidden=!category || category.name==="未分类";$("#category-error").textContent="";$("#category-dialog").showModal();form.elements.name.focus();}
function renderCategories(){
  const nav=$("#category-nav"),chips=$("#category-chips");nav.replaceChildren();chips.replaceChildren();
  const all=el("button",`category-chip ${!activeCategory?"active":""}`,"全部");all.addEventListener("click",()=>setView(view));chips.append(all);
  for(const c of categories){
    const count=projects.filter(p=>p.category===c.name).length;
    const row=el("div",`category-row color-${c.color} ${activeCategory===c.name?"active":""}`),button=el("button","category-button");
    const folder=el("span","category-folder");folder.append(icon("folder"));button.append(folder,el("span","category-name",c.name),el("span","category-count",count));button.addEventListener("click",()=>setView("all",c.name));
    row.append(button,buttonIcon("more",`管理分类 ${c.name}`,()=>openCategory(c),"icon-button category-edit"));nav.append(row);
    const chip=el("button",`category-chip color-${c.color} ${activeCategory===c.name?"active":""}`);chip.append(icon("folder"),document.createTextNode(c.name));chip.addEventListener("click",()=>setView(view,c.name));chips.append(chip);
  }
}
function filtered(){const query=$("#search").value.trim().toLowerCase();return projects.filter(p=>{
  if(view==="favorite"&&!p.favorite || view==="github"&&!isGitHub(p))return false;
  if(activeCategory&&p.category!==activeCategory)return false;
  if($("#status-filter").value&&p.status!==$("#status-filter").value)return false;
  return !query || [p.name,p.description,p.category,p.notes,p.local_path,p.repo_url,p.demo_url,p.url,...p.tags].join(" ").toLowerCase().includes(query);
}).sort((a,b)=>{if(a.favorite!==b.favorite)return Number(b.favorite)-Number(a.favorite);if($("#sort").value==="name")return a.name.localeCompare(b.name,"zh-CN");const key=$("#sort").value==="created"?"created_at":"updated_at";return b[key].localeCompare(a[key]) || b.id-a.id;});}
function render(){
  if(activeCategory&&!categories.some(c=>c.name===activeCategory))activeCategory="";
  const current=$("#quick-category").value;categoryOptions($("#quick-category"),activeCategory || current);
  document.querySelectorAll("[data-view]").forEach(b=>b.classList.toggle("active",view===b.dataset.view&&!activeCategory));
  $("#nav-total").textContent=projects.length;$("#nav-favorite").textContent=projects.filter(p=>p.favorite).length;$("#nav-github").textContent=projects.filter(isGitHub).length;
  const title=activeCategory || viewNames[view];$("#breadcrumb").textContent=title;$("#library-title").textContent=title;
  const heading=el("span","",view==="all"&&!activeCategory?"我的作品集":title);heading.append(el("span","title-dot","."));$("#view-title").replaceChildren(heading);
  renderCategories();const visible=filtered();$("#result-count").textContent=visible.length;$("#project-grid").replaceChildren(...visible.map(card));$("#empty").hidden=visible.length!==0;
  $("#empty h3").textContent=projects.length?"这个分类，还可以多一点作品":"从第一个作品开始";
  $("#empty-message").textContent=$("#search").value?"没有找到匹配的作品，试试其他关键词。":"粘贴一个项目网址，或把已有卡片移动到这里。";
}
function cover(p){
  const url=primaryUrl(p), theme=[...p.name].reduce((n,c)=>n+c.codePointAt(0),0)%6;
  const a=url?externalLink(url,undefined,`card-cover theme-${theme}`):el("button",`card-cover theme-${theme}`);a.setAttribute("aria-label",`${url?"打开":"查看"} ${p.name}`);if(!url)a.addEventListener("click",()=>showDetails(p.id));
  const fallback=el("div","cover-fallback"),symbol=el("span","cover-symbol");symbol.append(icon(isGitHub(p)?"github":url?"globe":"layers"));fallback.append(symbol,el("span","cover-name",p.name),el("span","cover-domain",domain(p)));a.append(fallback);
  if(p.cover_url){const image=el("img","card-cover-image");image.src=p.cover_url;image.alt=`${p.name} 封面`;image.loading="lazy";image.referrerPolicy="no-referrer";image.addEventListener("error",()=>image.remove());a.append(image);}
  a.append(el("span","cover-category",p.category));return a;
}
function card(p){
  const node=el("article",`card ${p.id===lastAdded?"new-card":""}`);node.dataset.id=p.id;
  const wrap=el("div","card-cover-wrap"),favorite=buttonIcon("star",`${p.favorite?"取消收藏":"收藏"} ${p.name}`,async()=>{
    favorite.disabled=true;try{await api(`/api/projects/${p.id}`,"PUT",{...p,favorite:!p.favorite});await refresh();}catch(e){notify(e.message);favorite.disabled=false;}
  },`icon-button card-favorite ${p.favorite?"selected":""}`);favorite.setAttribute("aria-pressed",p.favorite);wrap.append(cover(p),favorite);
  const body=el("div","card-body"),titleRow=el("div","card-title-row"),url=primaryUrl(p);
  const title=url?externalLink(url,p.name,"project-title"):el("button","project-title",p.name);if(!url)title.addEventListener("click",()=>showDetails(p.id));titleRow.append(title,el("span",`status ${statusClasses[p.status] || ""}`,p.status));
  const tags=el("div","card-tags");tags.append(...p.tags.slice(0,3).map(t=>el("span","tag",t)));
  const origin=el("div","card-origin");origin.append(icon(isGitHub(p)?"github":"globe"),el("span","",domain(p)));
  body.append(titleRow,el("p","card-description",p.description || "这是你收藏的一个作品。点击编辑，补充它的故事。"),tags,origin);
  const footer=el("div","card-footer"),select=el("select","card-category-select");select.setAttribute("aria-label",`${p.name} 的分类`);categoryOptions(select,p.category);select.addEventListener("change",async()=>{select.disabled=true;try{await api(`/api/projects/${p.id}`,"PUT",{...p,category:select.value});await refresh();notify("卡片已移动到新的分类");}catch(e){notify(e.message);select.disabled=false;select.value=p.category;}});
  const actions=el("div","card-footer-actions");
  const edit=buttonIcon("edit",`编辑 ${p.name}`,()=>openEditor(p),"card-edit-button");
  edit.append(el("span","","编辑"));
  actions.append(buttonIcon("info",`查看详情 ${p.name}`,()=>showDetails(p.id)),edit);
  if(url){const link=externalLink(url,undefined,"icon-button");link.append(icon("external"));link.title=`打开 ${p.name}`;link.setAttribute("aria-label",link.title);actions.append(link);}footer.append(select,actions);node.append(wrap,body,footer);return node;
}
function updateCover(){const form=$("#project-form"),value=form.elements.cover_url.value,box=$("#editor-cover");box.replaceChildren(icon("image"),el("span","","给作品选一张封面"));if(value){const image=el("img");image.src=value;image.alt="封面预览";image.referrerPolicy="no-referrer";image.addEventListener("error",()=>image.remove());box.append(image);}}
function openEditor(p){
  const form=$("#project-form");form.reset();form.querySelector("details").open=false;form.elements.id.value=p?.id || "";categoryOptions(form.elements.category,p?.category || activeCategory || "未分类");
  if(p){for(const field of fields)if(field!=="category")form.elements[field].value=p[field] || "";form.elements.url.value=primaryUrl(p);form.elements.tags.value=p.tags.join(", ");form.elements.favorite.checked=p.favorite;}
  $("#cover-link").value=p?.cover_url?.startsWith("http")?p.cover_url:"";$("#editor-error").textContent="";$("#editor-title").textContent=p?"编辑卡片":"手动记录作品";updateCover();$("#editor").showModal();form.elements.name.focus();
}
function showDetails(id){const p=projects.find(p=>p.id===id);if(!p)return;currentId=id;const content=$("#detail-content");content.replaceChildren();
  if(p.cover_url){const image=el("img","detail-cover");image.src=p.cover_url;image.alt=p.name;image.referrerPolicy="no-referrer";image.addEventListener("error",()=>image.remove());content.append(image);}
  const tags=el("div","detail-tags");tags.append(el("span","tag",p.category),el("span","tag",p.status),...p.tags.map(t=>el("span","tag",t)));content.append(el("h2","detail-title",p.name),tags,el("p","detail-text",p.description || "还没有作品介绍。"));
  const seen=new Set();for(const [url,label] of [[primaryUrl(p),"项目网址"],[p.repo_url,"代码仓库"],[p.demo_url,"在线演示"]])if(url&&!seen.has(url)){seen.add(url);content.append(externalLink(url,`${label} · ${url}`,"detail-link"));}
  if(p.local_path){const section=el("section","detail-section"),line=el("div","path-line"),copy=el("button","button secondary","复制");copy.addEventListener("click",async()=>{try{await navigator.clipboard.writeText(p.local_path);notify("路径已复制");}catch{notify("请选中路径后手动复制。");}});section.append(el("h3","","本地项目路径"));line.append(el("code","",p.local_path),copy);section.append(line);content.append(section);}
  const notes=el("section","detail-section");notes.append(el("h3","","开发笔记"),el("p","detail-text",p.notes || "还没有笔记。可以记下进度、问题或下一步计划。"));content.append(notes,el("p","muted",`创建于 ${new Date(p.created_at).toLocaleString("zh-CN")} · 更新于 ${new Date(p.updated_at).toLocaleString("zh-CN")}`));$("#details").showModal();
}
function focusQuick(){closeSidebar();$("#quick-url").focus();$("#quick-add-form").scrollIntoView({behavior:"smooth",block:"center"});}
document.querySelectorAll("[data-icon]").forEach(n=>n.replaceChildren(icon(n.dataset.icon)));
document.querySelectorAll("[data-close]").forEach(b=>b.addEventListener("click",()=>document.getElementById(b.dataset.close).close()));
document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>setView(b.dataset.view)));
$("#sidebar-toggle").addEventListener("click",()=>{$("#sidebar").classList.add("is-open");$("#sidebar-shade").hidden=false;$("#sidebar-toggle").setAttribute("aria-expanded","true");});$("#sidebar-shade").addEventListener("click",closeSidebar);
document.addEventListener("keydown",event=>{if(event.key==="Escape")closeSidebar();});
$("#new-category").addEventListener("click",()=>openCategory());$("#sidebar-add-category").addEventListener("click",()=>openCategory());
$("#new-project").addEventListener("click",focusQuick);$("#empty-add").addEventListener("click",focusQuick);$("#manual-open").addEventListener("click",()=>openEditor());
$("#search").addEventListener("input",render);["#status-filter","#sort"].forEach(s=>$(s).addEventListener("change",render));
function setLayout(list){$("#project-grid").classList.toggle("list-mode",list);$("#list-view").classList.toggle("active",list);$("#grid-view").classList.toggle("active",!list);$("#list-view").setAttribute("aria-pressed",list);$("#grid-view").setAttribute("aria-pressed",!list);}
$("#grid-view").addEventListener("click",()=>setLayout(false));$("#list-view").addEventListener("click",()=>setLayout(true));
$("#quick-add-form").addEventListener("submit",async event=>{
  event.preventDefault();const button=$("#quick-submit");button.disabled=true;button.lastElementChild.textContent="正在生成…";$("#quick-error").hidden=true;
  try{const result=await api("/api/links","POST",{url:$("#quick-url").value,category:$("#quick-category").value});lastAdded=result.project.id;view="all";activeCategory=result.project.category;$("#search").value="";$("#status-filter").value="";$("#quick-url").value="";await refresh();notify(result.metadata_loaded?"新卡片已生成，网站信息已读取":"卡片已生成。可以点击编辑，补充标题和自己的项目截图。");}
  catch(e){$("#quick-error").textContent=e.message;$("#quick-error").hidden=false;}
  finally{button.disabled=false;button.lastElementChild.textContent="生成卡片";}
});
$("#category-form").addEventListener("submit",async event=>{
  event.preventDefault();const form=event.currentTarget,original=form.elements.original.value;$("#save-category").disabled=true;
  try{const c=await api(original?`/api/categories/${encodeURIComponent(original)}`:"/api/categories",original?"PUT":"POST",{name:form.elements.name.value,color:form.elements.color.value});$("#category-dialog").close();activeCategory=c.name;view="all";await refresh();notify(original?"分类已更新":"新分类已创建，可以开始收藏作品了");closeSidebar();}
  catch(e){$("#category-error").textContent=e.message;}finally{$("#save-category").disabled=false;}
});
$("#delete-category").addEventListener("click",async()=>{const name=$("#category-form").elements.original.value;if(!confirm(`删除分类「${name}」？里面的作品会移到“未分类”，作品记录会保留。`))return;try{await api(`/api/categories/${encodeURIComponent(name)}`,"DELETE");$("#category-dialog").close();activeCategory="未分类";await refresh();notify("分类已删除，作品已移至未分类");}catch(e){$("#category-error").textContent=e.message;}});
$("#project-form").addEventListener("submit",async event=>{
  event.preventDefault();const form=event.currentTarget,data={};for(const field of fields)data[field]=form.elements[field].value;data.tags=[...new Set(form.elements.tags.value.split(/[,，]/).map(t=>t.trim()).filter(Boolean))];data.favorite=form.elements.favorite.checked;
  const id=form.elements.id.value;$("#save-project").disabled=true;
  try{if(data.url)data.url=window.LocalLibrary.normalizeUrl(data.url);await api(id?`/api/projects/${id}`:"/api/projects",id?"PUT":"POST",data);$("#editor").close();if(activeCategory&&data.category!==activeCategory)activeCategory=data.category;await refresh();notify("卡片已保存");}
  catch(e){$("#editor-error").textContent=e.message;}finally{$("#save-project").disabled=false;}
});
$("#read-metadata").addEventListener("click",async()=>{const form=$("#project-form"),button=$("#read-metadata");button.disabled=true;try{const result=await api("/api/preview","POST",{url:form.elements.url.value});form.elements.url.value=result.url;if(result.metadata_loaded){form.elements.name.value=result.name;form.elements.description.value=result.description;if(result.cover_url){form.elements.cover_url.value=result.cover_url;$("#cover-link").value=result.cover_url;updateCover();}notify("网站信息已读取，保存后更新卡片");}else{if(!form.elements.name.value)form.elements.name.value=result.name;notify(standalone?"网址已识别。免安装版可自行填写标题并上传项目截图。":"网站暂未提供可读取的信息，可以手动填写并保存。");}}catch(e){$("#editor-error").textContent=e.message;}finally{button.disabled=false;}});
$("#cover-link").addEventListener("change",()=>{$("#project-form").elements.cover_url.value=$("#cover-link").value;updateCover();});
$("#upload-cover").addEventListener("click",()=>$("#cover-file").click());$("#clear-cover").addEventListener("click",()=>{$("#project-form").elements.cover_url.value="";$("#cover-link").value="";updateCover();});
$("#cover-file").addEventListener("change",async event=>{const file=event.target.files[0];if(!file)return;try{
  if(!["image/png","image/jpeg","image/webp"].includes(file.type)||file.size>10*1024*1024)throw new Error("请选择 10 MB 以内的 PNG、JPEG 或 WebP 图片。");
  const bitmap=await createImageBitmap(file);const scale=Math.min(1,960/bitmap.width,960/bitmap.height),canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));canvas.getContext("2d").drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  let data=canvas.toDataURL("image/webp",.82);if(data.length>700000)data=canvas.toDataURL("image/jpeg",.6);if(data.length>700000)throw new Error("图片仍然过大，请选用较小的截图。");$("#project-form").elements.cover_url.value=data;$("#cover-link").value="";updateCover();notify("封面已选好，保存卡片后生效");
}catch(e){$("#editor-error").textContent=e.message;}finally{event.target.value="";}});
$("#detail-edit").addEventListener("click",()=>{$("#details").close();openEditor(projects.find(p=>p.id===currentId));});
$("#detail-delete").addEventListener("click",async()=>{const p=projects.find(p=>p.id===currentId);if(!p||!confirm(`确定删除「${p.name}」的卡片记录？`))return;try{await api(`/api/projects/${p.id}`,"DELETE");$("#details").close();await refresh();notify("卡片记录已删除");}catch(e){notify(e.message);}});
$("#backup-export").addEventListener("click",async()=>{try{const backup=await api("/api/export"),url=URL.createObjectURL(new Blob([JSON.stringify(backup,null,2)],{type:"application/json"})),a=el("a");a.href=url;a.download=`拾作备份-${new Date().toLocaleDateString("sv-SE")}.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify("备份已导出，包含卡片、分类和上传的封面");}catch(e){notify(e.message);}});
$("#backup-import").addEventListener("click",()=>$("#backup-file").click());
$("#backup-file").addEventListener("change",async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>50*1024*1024)throw new Error("备份文件不能超过 50 MB。");const data=JSON.parse(await file.text());if(data.format!=="project-collection"||![1,2].includes(data.version)||!Array.isArray(data.projects))throw new Error("请选择本工具导出的 JSON 备份。");if(!confirm(`从备份补充 ${data.projects.length} 张卡片？已有网址和相同记录会跳过，现有内容不会覆盖。`))return;const result=await api("/api/import","POST",data);view="all";activeCategory="";await refresh();notify(`新增 ${result.added} 张卡片，跳过 ${result.skipped} 条重复记录。`);}catch(e){notify(e instanceof SyntaxError?"备份不是有效的 JSON 文件。":e.message);}finally{event.target.value="";}});

function updateGitHubCount() {
  const count = $("#github-preview").querySelectorAll("input:checked").length;
  $("#github-confirm").textContent = `导入 ${count} 个项目`;
  $("#github-confirm").disabled = count === 0;
}
$("#github-open").addEventListener("click", () => $("#github-dialog").showModal());
$("#github-username").addEventListener("input", () => {
  githubPreview = []; previewOwner = "";
  $("#github-preview").replaceChildren(); $("#github-message").textContent = ""; updateGitHubCount();
});
$("#github-form").addEventListener("submit", async event => {
  event.preventDefault();
  const username = $("#github-username").value.trim();
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(username)) { $("#github-message").textContent = "请填写 GitHub 用户名，而非完整链接。"; return; }
  githubPreview = []; previewOwner = "";
  $("#github-preview").replaceChildren(); updateGitHubCount();
  $("#github-fetch").disabled = true; $("#github-message").textContent = "正在读取公开仓库，请稍候…";
  try {
    const result = await api(`/api/github?username=${encodeURIComponent(username)}`);
    if ($("#github-username").value.trim() !== username) return;
    githubPreview = result.projects; previewOwner = username;
    const source = result.source === "public-page" ? "从 GitHub 公开页面" : "";
    $("#github-message").textContent = result.truncated ? "仓库较多，本次读取的列表尚未完整。请选择要收录的项目。" : `${source}读取到 ${githubPreview.length} 个公开仓库，请选择要收录的项目。导入后可修改分类和实际进度。`;
    githubPreview.forEach((project, index) => {
      const row = el("div", "github-item"), label = el("label"), checkbox = el("input");
      checkbox.type = "checkbox"; checkbox.value = index; checkbox.checked = true;
      checkbox.addEventListener("change", updateGitHubCount);
      label.append(checkbox, document.createTextNode(project.name));
      row.append(label, el("span", "", project.tags[0] || "无语言标签")); $("#github-preview").append(row);
    });
    updateGitHubCount();
  } catch (error) { $("#github-message").textContent = error.message; }
  finally { $("#github-fetch").disabled = false; }
});
$("#github-confirm").addEventListener("click", async () => {
  if (!previewOwner || previewOwner !== $("#github-username").value.trim()) return;
  const selected = [...$("#github-preview").querySelectorAll("input:checked")].map(input => githubPreview[Number(input.value)]);
  if (!selected.length) return;
  $("#github-confirm").disabled = true;
  try {
    const result = await api("/api/import", "POST", {format: "project-collection", version: 1, projects: selected});
    $("#github-dialog").close(); view="all"; activeCategory=""; await refresh(); notify(`新增 ${result.added} 个项目，跳过 ${result.skipped} 个已有仓库。`);
  } catch (error) { $("#github-message").textContent = error.message; }
  finally { updateGitHubCount(); }
});


(async()=>{
  $("#runtime-mode").textContent=standalone?"浏览器本地保存 · 记得备份":"本机数据库保存";
  if(standalone)$("#quick-hint").textContent="直接生成网址卡片；可上传自己的项目截图作封面";
  try{const data=await api("/api/bootstrap");token=data.token;projects=data.projects;categories=data.categories;render();}
  catch(e){$("#load-error").textContent=e.message;$("#load-error").hidden=false;}
  finally{$("#loading").hidden=true;}
})();
