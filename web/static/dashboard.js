function showTab(name){
  document.querySelectorAll(".tab").forEach(t=>{
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".tabpane").forEach(p=>{
    p.classList.toggle("active", p.id === `tab-${name}`);
  });
}

document.addEventListener("DOMContentLoaded", ()=>{
  document.querySelectorAll(".tab").forEach(t=>{
    t.addEventListener("click", ()=> showTab(t.dataset.tab));
  });

  const search = document.getElementById("caseSearch");
  const list = document.getElementById("caseList");
  const filter = document.getElementById("caseFilter");

  function applyFilter(){
    const q = (search?.value || "").toLowerCase().trim();
    const f = (filter?.value || "all");
    if(!list) return;

    list.querySelectorAll(".item").forEach(el=>{
      const id = (el.dataset.id || "").toLowerCase();
      const name = (el.dataset.name || "").toLowerCase();
      const matchQ = !q || id.includes(q) || name.includes(q);

      // 지금은 모두 NEW로 보여주고 있으니 new 필터는 일단 동일 처리
      const matchF = (f === "all") || (f === "new");
      el.style.display = (matchQ && matchF) ? "" : "none";
    });
  }

  search?.addEventListener("input", applyFilter);
  filter?.addEventListener("change", applyFilter);
});
