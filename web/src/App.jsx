import React, { useCallback, useEffect, useMemo, useState } from 'react';
import AdminSales from './AdminSales.jsx';
import {
  Activity, ArrowDownToLine, ArrowLeft, ArrowRight, Check, CheckCircle2,
  CircleHelp, Clock3, Copy, Gauge, Globe2, KeyRound, Languages, LayoutDashboard,
  LoaderCircle, LockKeyhole, LogOut, Menu, MoreHorizontal, Plus, RefreshCw,
  Search, Settings, Shield, ShieldCheck, Trash2, UserRound, Users, X,
} from 'lucide-react';

const copy = {
  fa: {
    brand:'FORGE CONNECT', tagline:'پنل مدیریت خصوصی', overview:'نمای کلی', users:'کاربران', connections:'اتصال‌های فعال', settings:'تنظیمات', activity:'گزارش فعالیت', help:'راهنما', logout:'خروج از پنل',
    welcome:'سلام، خوش آمدی', overviewSub:'وضعیت سرویس و حساب‌های VPN را یک‌جا ببین.', addUser:'کاربر جدید', accounts:'حساب‌های VPN', viewAll:'مشاهده همه', totalUsers:'همه کاربران', activeUsers:'حساب‌های فعال', liveConnections:'اتصال هم‌زمان', vpnStatus:'وضعیت سرویس', online:'فعال', offline:'غیرفعال', noConnections:'در حال حاضر اتصالی برقرار نیست.',
    user:'کاربر', status:'وضعیت', devices:'اتصال‌ها', created:'تاریخ ساخت', actions:'عملیات', enabled:'فعال', disabled:'غیرفعال', connected:'متصل', disconnected:'قطع', search:'جست‌وجوی نام کاربری', noUsers:'هنوز کاربری ساخته نشده.', createFirst:'اولین حساب را بساز', addTitle:'ساخت حساب VPN', username:'نام کاربری', password:'رمز عبور', note:'یادداشت (اختیاری)', autoPassword:'خالی بماند تا رمز تصادفی ساخته شود', create:'ساخت حساب', cancel:'انصراف', resetPassword:'تغییر رمز', enable:'فعال‌سازی', disable:'غیرفعال‌سازی', delete:'حذف', confirmDelete:'این حساب و اتصال‌های فعالش حذف شوند؟', credentialsTitle:'اطلاعات اتصال', copy:'کپی', copied:'کپی شد', passwordOnce:'این رمز فقط همین‌بار نمایش داده می‌شود؛ آن را امن برای کاربر بفرست.', serverAddress:'آدرس سرور', vpnType:'نوع اتصال', caCertificate:'گواهی CA', downloadCA:'دریافت گواهی', strongSwan:'IKEv2 / strongSwan', searchEmpty:'نتیجه‌ای پیدا نشد.', loading:'در حال بارگذاری…', refresh:'تازه‌سازی', connection:'اتصال', remoteAddress:'آدرس مبدأ', virtualIP:'آدرس تونل', duration:'شناسه تونل', noAudit:'هنوز رویدادی ثبت نشده.', actor:'مدیر', event:'رویداد', subject:'موضوع', time:'زمان', security:'امنیت حساب مدیر', currentPassword:'رمز فعلی', newUsername:'نام کاربری جدید', newPassword:'رمز جدید', saveChanges:'ذخیره تغییرات', changeCredentials:'تغییر اطلاعات ورود', securityHint:'رمز مدیر حداقل ۱۴ نویسه باشد. با تغییر رمز، نشست‌های فعلی بسته می‌شوند.', domain:'دامنه پنل', ipv6:'IPv6', enabledText:'پیکربندی شده', unavailable:'در دسترس نیست', signIn:'ورود مدیر', signInSub:'برای ادامه به پنل VPN وارد شو.', setupTitle:'راه‌اندازی مدیر پنل', setupSub:'یک نام کاربری و رمز قوی برای حساب مدیریتی انتخاب کن.', setupToken:'کد یک‌بارمصرف راه‌اندازی', setupTokenHint:'این کد هنگام نصب در ترمینال نمایش داده شد.', createAdmin:'ساخت حساب مدیر', firstPassword:'حداقل ۱۴ نویسه', confirmPassword:'تکرار رمز عبور', passwordMismatch:'رمزها یکسان نیستند.', initialInfo:'این مرحله فقط یک بار انجام می‌شود. کد راه‌اندازی را از ترمینالی که install.sh را اجرا کردی بردار.', forgot:'برای کمک به راهنمای نصب مراجعه کن.', installWizard:'راه‌اندازی امن', adminCreated:'حساب مدیر ساخته شد.', genericError:'عملیات انجام نشد.', userCreated:'حساب ساخته شد.', passwordChanged:'رمز تغییر کرد و اتصال‌های قبلی بسته شدند.', userEnabled:'حساب فعال شد.', userDisabled:'حساب غیرفعال و اتصال‌هایش قطع شد.', userDeleted:'حساب حذف و اتصال‌هایش قطع شد.', adminSaved:'اطلاعات مدیر به‌روز شد.', vpnOnline:'strongSwan در حال اجراست.', vpnOffline:'سرویس strongSwan در دسترس نیست.', noNote:'—', back:'بازگشت', language:'English', close:'بستن',
  },
  en: {
    brand:'FORGE CONNECT', tagline:'PRIVATE ADMIN CONSOLE', overview:'Overview', users:'Users', connections:'Live sessions', settings:'Settings', activity:'Activity log', help:'Help', logout:'Sign out',
    welcome:'Welcome back', overviewSub:'A clear view of your VPN service and accounts.', addUser:'New user', accounts:'VPN accounts', viewAll:'View all', totalUsers:'Total users', activeUsers:'Enabled accounts', liveConnections:'Live sessions', vpnStatus:'Service status', online:'Online', offline:'Offline', noConnections:'No active connections right now.',
    user:'User', status:'Status', devices:'Sessions', created:'Created', actions:'Actions', enabled:'Enabled', disabled:'Disabled', connected:'Connected', disconnected:'Disconnected', search:'Search username', noUsers:'No VPN accounts yet.', createFirst:'Create your first account', addTitle:'Create VPN account', username:'Username', password:'Password', note:'Note (optional)', autoPassword:'Leave blank to generate a strong password', create:'Create account', cancel:'Cancel', resetPassword:'Reset password', enable:'Enable', disable:'Disable', delete:'Delete', confirmDelete:'Delete this account and disconnect its active sessions?', credentialsTitle:'Connection credentials', copy:'Copy', copied:'Copied', passwordOnce:'The password is shown once. Share it with the user securely.', serverAddress:'Server address', vpnType:'VPN protocol', caCertificate:'CA certificate', downloadCA:'Download certificate', strongSwan:'IKEv2 / strongSwan', searchEmpty:'No matches found.', loading:'Loading…', refresh:'Refresh', connection:'Connection', remoteAddress:'Remote address', virtualIP:'Tunnel address', duration:'Tunnel ID', noAudit:'No events recorded yet.', actor:'Admin', event:'Event', subject:'Subject', time:'Time', security:'Administrator security', currentPassword:'Current password', newUsername:'New username', newPassword:'New password', saveChanges:'Save changes', changeCredentials:'Update sign-in details', securityHint:'Use at least 14 characters. Changing your password signs out all existing sessions.', domain:'Panel domain', ipv6:'IPv6', enabledText:'Configured', unavailable:'Unavailable', signIn:'Admin sign in', signInSub:'Sign in to continue to the VPN console.', setupTitle:'Set up your admin account', setupSub:'Choose a username and strong password for the administrator.', setupToken:'One-time setup code', setupTokenHint:'The installer printed this code in the terminal.', createAdmin:'Create admin account', firstPassword:'At least 14 characters', confirmPassword:'Confirm password', passwordMismatch:'Passwords do not match.', initialInfo:'This is a one-time step. Find the setup code in the terminal where install.sh was run.', forgot:'See the installation guide for help.', installWizard:'Secure setup', adminCreated:'Admin account created.', genericError:'The request could not be completed.', userCreated:'Account created.', passwordChanged:'Password updated and existing sessions disconnected.', userEnabled:'Account enabled.', userDisabled:'Account disabled and sessions disconnected.', userDeleted:'Account deleted and sessions disconnected.', adminSaved:'Administrator details updated.', vpnOnline:'strongSwan is running.', vpnOffline:'strongSwan is unavailable.', noNote:'—', back:'Back', language:'فارسی', close:'Close',
  },
};

const iconMap = { overview:LayoutDashboard, users:Users, connections:Activity, settings:Settings, activity:Clock3 };

function App() {
  const [lang,setLang] = useState(localStorage.getItem('forge-connect-lang') || 'fa');
  const [csrf,setCsrf] = useState('');
  const [user,setUser] = useState('');
  const [setupRequired,setSetupRequired] = useState(false);
  const [screen,setScreen] = useState('loading');
  const [page,setPage] = useState('overview');
  const [dashboard,setDashboard] = useState(null);
  const [users,setUsers] = useState([]);
  const [connections,setConnections] = useState([]);
  const [audit,setAudit] = useState([]);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState('');
  const [toast,setToast] = useState('');
  const [modal,setModal] = useState('');
  const [selected,setSelected] = useState(null);
  const [search,setSearch] = useState('');
  const [mobileMenu,setMobileMenu] = useState(false);

  const t = copy[lang];
  const api = useCallback(async (path, options={}) => {
    const headers = { 'Content-Type':'application/json', ...(options.headers || {}) };
    if (csrf && options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrf;
    const response = await fetch(path,{ credentials:'same-origin', ...options, headers });
    const type = response.headers.get('content-type') || '';
    if (type.includes('application/json')) {
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || t.genericError);
      return body;
    }
    if (!response.ok) throw new Error(t.genericError);
    return response;
  },[csrf,t.genericError]);

  const refresh = useCallback(async (target=page) => {
    setLoading(true); setError('');
    try {
      if (target === 'overview') {
        const [d,c,u] = await Promise.all([api('/api/dashboard'),api('/api/connections'),api('/api/users')]);
        setDashboard(d); setConnections(c.connections); setUsers(u.users);
      } else if (target === 'users') {
        const result = await api('/api/users'); setUsers(result.users);
      } else if (target === 'connections') {
        const result = await api('/api/connections'); setConnections(result.connections);
      } else if (target === 'activity') {
        const result = await api('/api/audit'); setAudit(result.events);
      } else if (target === 'settings') {
        const result = await api('/api/dashboard'); setDashboard(result);
      }
    } catch (e) {
      if (String(e.message).includes('دوباره وارد شو') || String(e.message).includes('sign in again')) setScreen('login');
      else setError(e.message);
    } finally { setLoading(false); }
  },[api,page]);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr';
    localStorage.setItem('forge-connect-lang',lang);
  },[lang]);

  useEffect(() => {
    (async () => {
      try {
        const info = await api('/api/bootstrap'); setSetupRequired(info.setupRequired);
        if (info.setupRequired) { setScreen('setup'); return; }
        const me = await api('/api/me'); setCsrf(me.csrf); setUser(me.username); setScreen('app');
      } catch { setScreen('login'); }
    })();
  },[]);

  useEffect(() => { if (screen==='app') refresh(page); },[screen,page,refresh]);
  useEffect(() => { if (!toast) return; const id=setTimeout(()=>setToast(''),3600); return ()=>clearTimeout(id); },[toast]);

  async function submitLogin(event) {
    event.preventDefault(); setError('');
    const form = new FormData(event.currentTarget);
    try {
      const result = await api('/api/login',{method:'POST',body:JSON.stringify({username:form.get('username'),password:form.get('password')})});
      setCsrf(result.csrf); setUser(result.username); setScreen('app'); setPage('overview');
    } catch(e) { setError(e.message); }
  }
  async function submitSetup(event) {
    event.preventDefault(); setError('');
    const form = new FormData(event.currentTarget);
    if (form.get('password') !== form.get('confirm')) { setError(t.passwordMismatch); return; }
    try {
      const result=await api('/api/setup/admin',{method:'POST',body:JSON.stringify({username:form.get('username'),password:form.get('password'),setupToken:form.get('token')})});
      setCsrf(result.csrf); setUser(result.username); setScreen('app'); setToast(t.adminCreated);
    } catch(e) { setError(e.message); }
  }
  async function action(path,method,body,success) {
    setError('');
    try { const result=await api(path,{method,body:body===undefined?undefined:JSON.stringify(body)}); if(result.csrf)setCsrf(result.csrf); if(result.username && method==='POST'){}; setToast(success); setModal(''); await refresh(page); return result; }
    catch(e){setError(e.message);throw e;}
  }
  async function logout() {
    try { await api('/api/logout',{method:'POST',body:'{}'}); } catch {}
    setCsrf(''); setUser(''); setScreen('login');
  }
  function changePage(key) { setPage(key); setMobileMenu(false); setError(''); }

  if (screen==='loading') return <div className="loading-screen"><LoaderCircle className="spin" size={22}/><span>{t.loading}</span></div>;
  if (screen==='setup') return <AuthFrame lang={lang} setLang={setLang} t={t} title={t.setupTitle} subtitle={t.setupSub} icon={<ShieldCheck size={23}/> }>
    <form className="auth-form" onSubmit={submitSetup}>
      <label>{t.setupToken}<input name="token" autoComplete="one-time-code" required placeholder="••••••••••••"/></label>
      <div className="field-help">{t.initialInfo}</div>
      <label>{t.username}<input name="username" required minLength="3" maxLength="32" autoComplete="username"/></label>
      <label>{t.password}<input name="password" type="password" required minLength="14" maxLength="128" autoComplete="new-password" placeholder={t.firstPassword}/></label>
      <label>{t.confirmPassword}<input name="confirm" type="password" required minLength="14" maxLength="128" autoComplete="new-password"/></label>
      {error&&<div className="form-error">{error}</div>}
      <button className="button primary full" type="submit">{t.createAdmin}<ArrowLeft size={17}/></button>
    </form>
  </AuthFrame>;
  if (screen==='login') return <AuthFrame lang={lang} setLang={setLang} t={t} title={t.signIn} subtitle={t.signInSub} icon={<LockKeyhole size={22}/> }>
    <form className="auth-form" onSubmit={submitLogin}>
      <label>{t.username}<input name="username" autoComplete="username" required/></label>
      <label>{t.password}<input name="password" type="password" autoComplete="current-password" required/></label>
      {error&&<div className="form-error">{error}</div>}
      <button className="button primary full" type="submit">{t.signIn}<ArrowLeft size={17}/></button>
    </form>
    <div className="auth-foot"><Shield size={15}/>{t.forgot}</div>
  </AuthFrame>;

  const nav = [
    ['overview','overview',LayoutDashboard],['users','users',Users],['connections','connections',Activity],
    ['settings','settings',Settings],['activity','activity',Clock3],
  ];
  const title = t[page];
  const filteredUsers=users.filter(u=>u.username.toLowerCase().includes(search.toLowerCase()));
  return <div className={`app-shell ${mobileMenu?'menu-open':''}`}>
    {mobileMenu&&<button className="mobile-scrim" aria-label={t.close} onClick={()=>setMobileMenu(false)}/>}
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><ShieldCheck size={20}/></div><div><strong>{t.brand}</strong><small>{t.tagline}</small></div><button className="icon-button sidebar-close" onClick={()=>setMobileMenu(false)}><X size={18}/></button></div>
      <div className="nav-caption">{lang==='fa'?'فضای کاری':'WORKSPACE'}</div>
      <nav>{nav.map(([key,label,Icon])=><button key={key} onClick={()=>changePage(key)} className={`nav-item ${page===key?'active':''}`}><Icon size={18}/><span>{t[label]}</span>{key==='connections'&&connections.length>0&&<i>{connections.length}</i>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="server-chip"><span className={`status-dot ${dashboard?.vpnStatus==='active'?'good':'bad'}`}/><div><strong>{dashboard?.vpnStatus==='active'?t.online:t.offline}</strong><small>{dashboard?.domain || '—'}</small></div><MoreHorizontal size={17}/></div><button className="nav-item logout" onClick={logout}><LogOut size={18}/><span>{t.logout}</span></button></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="topbar-left"><button className="icon-button menu-trigger" onClick={()=>setMobileMenu(true)}><Menu size={20}/></button><div className="breadcrumb"><span>{t.brand}</span><span className="slash">/</span><strong>{title}</strong></div></div><div className="topbar-actions"><button className="lang-button" onClick={()=>setLang(lang==='fa'?'en':'fa')}><Languages size={16}/><span>{t.language}</span></button><div className="topbar-separator"/><div className="profile"><div className="profile-avatar">{user.slice(0,1).toUpperCase()}</div><span>{user}</span></div></div></header>
      <div className="content">
        {error&&<div className="alert error"><CircleHelp size={17}/><span>{error}</span><button onClick={()=>setError('')}><X size={16}/></button></div>}
        {page==='overview'&&<>
          <div className="page-heading"><div><div className="eyebrow">{lang==='fa'?'داشبورد مدیریتی':'ADMIN CONSOLE'}</div><h1>{t.welcome}</h1><p>{t.overviewSub}</p></div><button className="button secondary" onClick={()=>refresh()} disabled={loading}><RefreshCw size={16} className={loading?'spin':''}/>{t.refresh}</button></div>
          <div className="stats-grid">
            <StatCard title={t.totalUsers} value={dashboard?.totalUsers??'—'} hint={t.accounts} icon={Users} tone="blue"/>
            <StatCard title={t.activeUsers} value={dashboard?.enabledUsers??'—'} hint={`${dashboard?.totalUsers ? Math.round(dashboard.enabledUsers/dashboard.totalUsers*100):0}%`} icon={ShieldCheck} tone="green"/>
            <StatCard title={t.liveConnections} value={dashboard?.activeConnections??'—'} hint={t.connected} icon={Activity} tone="amber"/>
            <StatCard title={t.vpnStatus} value={dashboard?.vpnStatus==='active'?t.online:t.offline} hint={dashboard?.domain||'—'} icon={Gauge} tone={dashboard?.vpnStatus==='active'?'green':'red'} compact/>
          </div>
          <section className="panel-card users-preview"><div className="section-head"><div><h2>{t.accounts}</h2><p>{lang==='fa'?'آخرین حساب‌های مدیریت‌شده':'Recently managed accounts'}</p></div><div className="head-actions"><button className="text-button" onClick={()=>changePage('users')}>{t.viewAll}{lang==='fa'?<ArrowLeft size={15}/>:<ArrowRight size={15}/>}</button><button className="button primary" onClick={()=>{setModal('add');setSelected(null)}}><Plus size={17}/>{t.addUser}</button></div></div><UsersTable users={users.slice(0,5)} t={t} lang={lang} onPassword={u=>{setSelected(u);setModal('password')}} onConfigure={u=>{setSelected(u);setModal('edit')}} onToggle={toggleUser} onDelete={deleteUser}/></section>
          <section className="panel-card connection-preview"><div className="section-head"><div><h2>{t.connections}</h2><p>{lang==='fa'?'نشست‌های فعال روی سرور':'Active sessions on the server'}</p></div><button className="text-button" onClick={()=>changePage('connections')}>{t.viewAll}{lang==='fa'?<ArrowLeft size={15}/>:<ArrowRight size={15}/>}</button></div><ConnectionsTable rows={connections.slice(0,5)} t={t} lang={lang}/></section>
        </>}
        {page==='users'&&<><section className="panel-card certificate-shortcut"><div className="certificate-row"><div><strong>{t.caCertificate}</strong><small>{lang==='fa'?'برای اتصال کاربران، این گواهی را روی دستگاهشان نصب کنید.':'Install this CA certificate on each client device.'}</small></div><a className="button secondary" href="/api/ca"><ArrowDownToLine size={16}/>{t.downloadCA}</a></div></section><div className="page-heading"><div><div className="eyebrow">{lang==='fa'?'دسترسی‌ها':'ACCESS CONTROL'}</div><h1>{t.accounts}</h1><p>{lang==='fa'?'سهمیه، اعتبار، پروتکل و سقف اتصال هر حساب را تنظیم کن.':'Set each account’s quota, validity, protocols and connection limit.'}</p></div><button className="button primary" onClick={()=>{setModal('add');setSelected(null)}}><Plus size={17}/>{t.addUser}</button></div><section className="panel-card"><div className="list-toolbar"><div className="search-box"><Search size={17}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder={t.search}/>{search&&<button onClick={()=>setSearch('')}><X size={14}/></button>}</div><span className="result-count">{filteredUsers.length} {lang==='fa'?'حساب':'accounts'}</span></div><UsersTable users={filteredUsers} t={t} lang={lang} onPassword={u=>{setSelected(u);setModal('password')}} onConfigure={u=>{setSelected(u);setModal('edit')}} onToggle={toggleUser} onDelete={deleteUser}/>{filteredUsers.length===0&&users.length===0&&<EmptyState t={t} onClick={()=>setModal('add')}/>}</section></>}
        {page==='connections'&&<><div className="page-heading"><div><div className="eyebrow">{lang==='fa'?'وضعیت زنده':'LIVE STATUS'}</div><h1>{t.connections}</h1><p>{lang==='fa'?'نشست‌های فعال IKEv2، WireGuard و OpenConnect':'Active IKEv2, WireGuard and OpenConnect sessions.'}</p></div><button className="button secondary" onClick={()=>refresh()} disabled={loading}><RefreshCw size={16} className={loading?'spin':''}/>{t.refresh}</button></div><section className="panel-card"><ConnectionsTable rows={connections} t={t} lang={lang} full/></section></>}
        {page==='settings'&&<><div className="page-heading"><div><div className="eyebrow">{lang==='fa'?'حساب و سرور':'ACCOUNT & SERVER'}</div><h1>{t.settings}</h1><p>{lang==='fa'?'امنیت ورود مدیر و اطلاعات سرور را مدیریت کن.':'Manage administrator security and server details.'}</p></div></div><div className="settings-grid"><section className="panel-card settings-card"><div className="settings-title"><div className="settings-icon"><KeyRound size={19}/></div><div><h2>{t.security}</h2><p>{t.securityHint}</p></div></div><form className="settings-form" onSubmit={saveAdmin}><label>{t.currentPassword}<input name="currentPassword" type="password" required autoComplete="current-password"/></label><label>{t.newUsername}<input name="username" defaultValue={user} required minLength="3" maxLength="32" autoComplete="username"/></label><label>{t.newPassword}<input name="newPassword" type="password" required minLength="14" maxLength="128" autoComplete="new-password"/></label><div className="form-end"><button className="button primary" type="submit">{t.saveChanges}</button></div></form></section><section className="panel-card settings-card"><div className="settings-title"><div className="settings-icon"><Globe2 size={19}/></div><div><h2>{lang==='fa'?'اطلاعات اتصال':'Connection details'}</h2><p>{lang==='fa'?'این مشخصات را برای اتصال کاربران بفرست.':'Share these details with VPN users.'}</p></div></div><InfoLine label={t.serverAddress} value={dashboard?.domain||'—'} copyable/><InfoLine label={t.vpnType} value={t.strongSwan+' + WireGuard + OpenConnect :8443'}/><InfoLine label={t.ipv6} value={dashboard?.ipv6Enabled?t.enabledText:t.unavailable}/><div className="certificate-row"><div><strong>{t.caCertificate}</strong><small>{lang==='fa'?'برای اولین اتصال باید روی دستگاه نصب شود.':'Install it on the client device before connecting.'}</small></div><a className="button secondary" href="/api/ca"><ArrowDownToLine size={16}/>{t.downloadCA}</a></div></section></div><AdminSales api={api} lang={lang}/></>}
        {page==='activity'&&<><div className="page-heading"><div><div className="eyebrow">{lang==='fa'?'ردیابی تغییرات':'CHANGE HISTORY'}</div><h1>{t.activity}</h1><p>{lang==='fa'?'تغییرات مدیریتی اخیر':'Recent administrator actions.'}</p></div><button className="button secondary" onClick={()=>refresh()} disabled={loading}><RefreshCw size={16}/>{t.refresh}</button></div><section className="panel-card"><AuditTable rows={audit} t={t} lang={lang}/></section></>}
      </div>
    </main>
    {(modal==='add'||modal==='edit')&&<UserModal mode={modal} selected={selected} t={t} lang={lang} onClose={()=>setModal('')} onSubmit={modal==='add'?createUser:configureUser}/>}
    {modal==='password'&&selected&&<UserModal mode="password" selected={selected} t={t} lang={lang} onClose={()=>setModal('')} onSubmit={resetPassword}/>}
    {modal==='credentials'&&selected&&<CredentialsModal info={selected} t={t} lang={lang} onClose={()=>setModal('')}/>}
    {toast&&<div className="toast"><CheckCircle2 size={17}/>{toast}</div>}
  </div>;

  async function createUser(data) {
    const result=await action('/api/users','POST',data,t.userCreated);
    setSelected({username:result.username,password:result.password,portalUrl:result.portalUrl,protocols:result.protocols,wireguardConfig:result.wireguardConfig||''}); setModal('credentials');
  }
  async function configureUser(item,data) { await action(`/api/users/${item.id}`,'PATCH',data,lang==='fa'?'تنظیمات حساب ذخیره شد.':'Account settings saved.'); }
  async function resetPassword(item,data) {
    const result=await action(`/api/users/${item.id}/password`,'POST',data,t.passwordChanged);
    setSelected({username:result.username,password:result.password}); setModal('credentials');
  }
  async function toggleUser(item) {
    await action(`/api/users/${item.id}`,'PATCH',{enabled:!item.enabled},item.enabled?t.userDisabled:t.userEnabled);
  }
  async function deleteUser(item) {
    if (!window.confirm(t.confirmDelete)) return;
    await action(`/api/users/${item.id}`,'DELETE',undefined,t.userDeleted);
  }
  async function saveAdmin(event) {
    event.preventDefault(); const form=new FormData(event.currentTarget);
    const result=await action('/api/admin/credentials','POST',{currentPassword:form.get('currentPassword'),username:form.get('username'),newPassword:form.get('newPassword')},t.adminSaved);
    setUser(result.username); setCsrf(result.csrf);
  }
}

function AuthFrame({lang,setLang,t,title,subtitle,icon,children}) {
  return <div className="auth-shell"><div className="auth-top"><div className="brand"><div className="brand-mark"><ShieldCheck size={20}/></div><div><strong>{t.brand}</strong><small>{t.tagline}</small></div></div><button className="lang-button" onClick={()=>setLang(lang==='fa'?'en':'fa')}><Languages size={16}/>{t.language}</button></div><section className="auth-card"><div className="auth-icon">{icon}</div><h1>{title}</h1><p>{subtitle}</p>{children}</section><div className="auth-bottom"><LockKeyhole size={14}/>{lang==='fa'?'اتصال رمزنگاری‌شده · دسترسی مدیر':'Encrypted connection · administrator access'}</div></div>;
}

function StatCard({title,value,hint,icon:Icon,tone,compact}) {
  return <article className="stat-card"><div className={`stat-icon ${tone}`}><Icon size={19}/></div><div className="stat-main"><span>{title}</span><strong className={compact?'compact':''}>{value}</strong><small>{hint}</small></div></article>;
}

function UsersTable({users,t,lang,onPassword,onConfigure,onToggle,onDelete}) {
  if (!users.length) return null;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>{t.user}</th><th>{t.status}</th><th>{lang==='fa'?'IKEv2 / WG / OpenConnect':'IKEv2 / WG / OpenConnect'}</th><th>{lang==='fa'?'مصرف / سهمیه':'Used / quota'}</th><th>{t.created}</th><th>{t.actions}</th></tr></thead><tbody>{users.map(row=><tr key={row.id}><td><div className="user-cell"><div className="user-avatar">{row.username.slice(0,1).toUpperCase()}</div><div><strong>{row.username}</strong><small>{row.note||t.noNote}</small></div></div></td><td><span className={`badge ${row.enabled?'success':'muted'}`}><i/>{row.enabled?t.enabled:t.disabled}</span></td><td className="date-cell"><span>{lang==='fa'?'نشست':'Sessions'} {row.ikeConnections}/{row.maxConnections}</span><br/><small>WG {row.wireguardDevices}/{row.maxConnections}</small><br/><small>OC {row.ocservConnections}/{row.maxConnections}</small></td><td className="date-cell">{(row.usedBytes/1e9).toFixed(1)} / {row.quotaBytes?(row.quotaBytes/1e9).toFixed(0):'∞'} GB</td><td className="date-cell">{formatDate(row.createdAt,lang)}</td><td><div className="row-actions"><button className="icon-button" title={lang==='fa'?'تنظیم سهمیه و دستگاه‌ها':'Quota and device settings'} onClick={()=>onConfigure(row)}><Settings size={16}/></button><button className="icon-button" title={t.resetPassword} onClick={()=>onPassword(row)}><KeyRound size={16}/></button><button className="icon-button" title={row.enabled?t.disable:t.enable} onClick={()=>onToggle(row)}>{row.enabled?<LockKeyhole size={16}/>:<ShieldCheck size={16}/>}</button><button className="icon-button danger-icon" title={t.delete} onClick={()=>onDelete(row)}><Trash2 size={16}/></button></div></td></tr>)}</tbody></table></div>;
}

function ConnectionsTable({rows,t,lang,full=false}) {
  if (!rows.length) return <div className="empty-state"><div className="empty-icon"><Activity size={22}/></div><strong>{t.noConnections}</strong><span>{lang==='fa'?'به‌محض اتصال کاربران، اینجا نمایش داده می‌شود.':'Sessions will appear here when clients connect.'}</span></div>;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>{t.user}</th><th>{t.status}</th><th>{t.remoteAddress}</th><th>{t.virtualIP}</th><th>{t.duration}</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td><div className="user-cell"><div className="user-avatar small-avatar"><UserRound size={15}/></div><strong>{row.username}</strong></div></td><td><span className="badge success"><i/>{t.connected}</span></td><td className="mono">{row.remote}</td><td className="mono">{row.virtualAddresses||'—'}</td><td className="mono">{row.protocol||`IKE #${row.id}`}</td></tr>)}</tbody></table></div>;
}

function AuditTable({rows,t,lang}) {
  const labels={user_created:lang==='fa'?'ساخت کاربر':'Created user',user_enabled:lang==='fa'?'فعال‌سازی کاربر':'Enabled user',user_disabled:lang==='fa'?'غیرفعال‌سازی کاربر':'Disabled user',user_deleted:lang==='fa'?'حذف کاربر':'Deleted user',user_password_reset:lang==='fa'?'تغییر رمز VPN':'Reset VPN password',admin_credentials_changed:lang==='fa'?'تغییر ورود مدیر':'Changed admin sign-in',setup:lang==='fa'?'راه‌اندازی پنل':'Panel setup'};
  if(!rows.length)return <div className="empty-state"><div className="empty-icon"><Clock3 size={22}/></div><strong>{t.noAudit}</strong></div>;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>{t.event}</th><th>{t.subject}</th><th>{t.actor}</th><th>{t.time}</th></tr></thead><tbody>{rows.map((row,i)=><tr key={i}><td><span className="audit-event"><span className="event-mark"><Check size={14}/></span>{labels[row.action]||row.action}</span></td><td>{row.subject||'—'}</td><td>{row.actor}</td><td className="date-cell">{formatDate(row.createdAt,lang)}</td></tr>)}</tbody></table></div>;
}

function UserModal({mode,selected,t,lang,onClose,onSubmit}) {
  const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  async function submit(event) { event.preventDefault(); setBusy(true);setError('');const form=new FormData(event.currentTarget);const data={};if(mode==='add'){data.username=form.get('username');data.password=form.get('password');data.note=form.get('note')}if(mode==='add'||mode==='edit'){if(form.get('quotaGB')!=='')data.quotaGB=Number(form.get('quotaGB'));if(form.get('days')!=='')data.days=Number(form.get('days'));if(form.get('maxConnections')!=='')data.maxConnections=Number(form.get('maxConnections'));const ps=form.getAll('protocols');if(ps.length)data.protocols=ps}else data.password=form.get('password');try{await onSubmit(mode==='add'?data:selected,data)}catch(e){setError(e.message)}finally{setBusy(false)} }
  const edit=mode==='edit';
  return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className="modal-card"><div className="modal-head"><div className="modal-icon"><UserRound size={19}/></div><div><h2>{mode==='add'?t.addTitle:edit?(lang==='fa'?'تنظیمات حساب':'Account settings'):t.resetPassword}</h2>{selected&&<p>{selected.username}</p>}</div><button className="icon-button" onClick={onClose}><X size={19}/></button></div><form onSubmit={submit} className="modal-form">{mode==='add'&&<><label>{t.username}<input name="username" required minLength="3" maxLength="32" autoFocus autoComplete="off"/></label><label>{t.note}<input name="note" maxLength="120"/></label></>}{(mode==='add'||edit)&&<><div className="sales-fields"><label>{lang==='fa'?'سهمیه GB (صفر=نامحدود)':'Quota GB (0=unlimited)'}<input name="quotaGB" type="number" min="0" step="0.1" defaultValue={edit?selected.quotaBytes/1e9:30}/></label><label>{lang==='fa'?'اعتبار روز جدید (خالی=بدون تغییر)':'New validity days (blank=keep)'}<input name="days" type="number" min="0" max="3650" defaultValue={edit?'':30}/></label><label>{lang==='fa'?'سقف نشست هم‌زمان':'Simultaneous limit'}<input name="maxConnections" type="number" min="1" max="50" defaultValue={edit?selected.maxConnections:1}/></label></div><fieldset className="protocol-options"><legend>{lang==='fa'?'پروتکل‌های مجاز':'Allowed protocols'}</legend><label><input type="checkbox" name="protocols" value="ikev2" defaultChecked={!edit||selected.protocols?.includes('ikev2')}/> IKEv2</label><label><input type="checkbox" name="protocols" value="wireguard" defaultChecked={!edit||selected.protocols?.includes('wireguard')}/> WireGuard</label><label><input type="checkbox" name="protocols" value="ocserv" defaultChecked={!edit||selected.protocols?.includes('ocserv')}/> OpenConnect</label></fieldset></>}{mode!=='edit'&&<><label>{mode==='add'?t.password:t.newPassword}<input name="password" type="password" minLength="4" maxLength="128" placeholder={t.autoPassword} autoComplete="new-password"/></label><div className="field-help">{lang==='fa'?'رمز حداقل ۴ نویسه؛ خالی بماند تا رمز تصادفی ساخته شود.':'At least 4 characters. Leave blank to generate one.'}</div></>}{error&&<div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>{t.cancel}</button><button className="button primary" disabled={busy}>{busy?<LoaderCircle size={17} className="spin"/>:<Check size={17}/>}{mode==='add'?t.create:t.saveChanges}</button></div></form></section></div>;
}

function CredentialsModal({info,t,lang,onClose}) {
  const [copied,setCopied]=useState(false);const [error,setError]=useState('');
  const all=`Server: ${window.location.hostname}\nVPN types: ${(info.protocols||['ikev2']).map(p=>({ikev2:'IKEv2',wireguard:'WireGuard',ocserv:'OpenConnect (port 8443)'}[p])).join(', ')}\nUsername: ${info.username}\nPassword: ${info.password}\nUser portal: ${info.portalUrl||window.location.origin+'/portal'}`;
  async function copyAll(){try{await navigator.clipboard.writeText(all);setCopied(true);setTimeout(()=>setCopied(false),1600)}catch{setError(lang==='fa'?'کپی خودکار در دسترس نیست.':'Clipboard unavailable.')}}
  function downloadWg(){if(!info.wireguardConfig)return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([info.wireguardConfig],{type:'text/plain'}));a.download=`forge-connect-${info.username}.conf`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
  return <div className="modal-backdrop"><section className="modal-card credentials-modal"><div className="credential-success"><div><Check size={23}/></div><h2>{t.credentialsTitle}</h2><p>{t.passwordOnce}</p></div><div className="credential-grid"><Credential label={t.serverAddress} value={window.location.hostname}/><Credential label={t.vpnType} value={(info.protocols||['ikev2']).map(p=>({ikev2:'IKEv2',wireguard:'WireGuard',ocserv:'OpenConnect'}[p])).join(' + ')}/><Credential label={t.username} value={info.username}/><Credential label={t.password} value={info.password} secret/><Credential label={lang==='fa'?'پورتال کاربر':'User portal'} value={info.portalUrl||window.location.origin+'/portal'}/></div>{info.wireguardConfig&&<div className="certificate-row"><div><strong>WireGuard</strong><small>{lang==='fa'?'یک پروفایل آماده هم‌زمان با ساخت حساب ایجاد شد.':'One profile was created with this account.'}</small></div><button className="button secondary" onClick={downloadWg}><ArrowDownToLine size={16}/>{lang==='fa'?'دانلود .conf':'Download .conf'}</button></div>}{error&&<div className="form-error">{error}</div>}<div className="modal-actions"><button className="button secondary" onClick={onClose}>{t.close}</button><button className="button primary" onClick={copyAll}>{copied?<Check size={17}/>:<Copy size={17}/>}{copied?t.copied:t.copy}</button></div></section></div>;
}
function Credential({label,value,secret}){return <div className="credential-item"><span>{label}</span><code className={secret?'secret':''}>{value}</code></div>}
function InfoLine({label,value,copyable}) { const [copied,setCopied]=useState(false);async function copy(){try{await navigator.clipboard.writeText(value);setCopied(true);setTimeout(()=>setCopied(false),1200)}catch{}}return <div className="info-line"><span>{label}</span><div><code>{value}</code>{copyable&&<button className="icon-button" onClick={copy} title="Copy">{copied?<Check size={15}/>:<Copy size={15}/>}</button>}</div></div> }
function EmptyState({t,onClick}) {return <div className="empty-state"><div className="empty-icon"><Users size={22}/></div><strong>{t.noUsers}</strong><button className="button primary" onClick={onClick}><Plus size={16}/>{t.createFirst}</button></div>}
function formatDate(value,lang){try{return new Intl.DateTimeFormat(lang==='fa'?'fa-IR':'en-US',{dateStyle:'medium'}).format(new Date(value))}catch{return value}}

export default App;
