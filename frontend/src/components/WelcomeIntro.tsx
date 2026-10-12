import {useCallback, useEffect, useRef, useState} from "react";
import type {MouseEvent} from "react";
import {CONDITION_LABELS, CONDITION_ORDER} from "../conditionCards";
import {hasDismissedWelcome, rememberWelcomeDismissed} from "../welcomeIntro";
import {ConditionIcon} from "./ConditionIcon";
import "../welcomeIntro.css";

function sessionStore(): Storage | null { try { return window.sessionStorage; } catch { return null; } }

function TechnologyIcon({type}: {type: "ai" | "twin" | "gis"}) {
  return <svg className={`welcome-tech-icon welcome-tech-icon--${type}`} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {type === "ai" && <><rect x="8" y="8" width="16" height="16" rx="4"/><path d="M12 3v5m8-5v5M12 24v5m8-5v5M3 12h5m-5 8h5m16-8h5m-5 8h5"/><path d="m13 18 3-6 3 6m-5-2h4"/></>}
    {type === "twin" && <><path d="m16 3 12 7v13l-12 7L4 23V10Z"/><path d="m4 10 12 7 12-7M16 17v13"/></>}
    {type === "gis" && <><path d="m3 13 8-3 10 3 8-3v17l-8 3-10-3-8 3Z"/><path d="M11 16v11m10-9v12"/><path d="M22 7c0 4-6 9-6 9S10 11 10 7a6 6 0 1 1 12 0Z"/><circle cx="16" cy="7" r="2"/></>}
  </svg>;
}

export function WelcomeIntro() {
  const [open, setOpen] = useState(() => !hasDismissedWelcome(sessionStore()));
  const dialog = useRef<HTMLDialogElement>(null);
  const dismiss = useCallback(() => { rememberWelcomeDismissed(sessionStore()); setOpen(false); }, []);
  function dismissFromBackdrop(event: MouseEvent<HTMLDialogElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const outside = event.clientX < bounds.left || event.clientX > bounds.right
      || event.clientY < bounds.top || event.clientY > bounds.bottom;
    if (outside) dismiss();
  }

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    else if (!open && element.open) element.close();
  }, [open]);
  return <dialog ref={dialog} className="welcome-dialog" aria-labelledby="welcome-title" aria-describedby="welcome-description"
      onCancel={(event) => { event.preventDefault(); dismiss(); }} onClose={dismiss} onClick={dismissFromBackdrop}>
      <header className="welcome-header">
        <img className="welcome-company" src="/branding/ltmetric.png" alt="엘티메트릭" width="180" height="60"/>
        <button className="welcome-close" type="button" aria-label="서비스 소개 닫기" onClick={dismiss} autoFocus>×</button>
      </header>
      <h1 className="welcome-title" id="welcome-title">안전 골목길</h1>
      <p className="welcome-subtitle">골목에 안전을 더하다</p>
      <div className="welcome-technologies" aria-label="핵심 기술">
        <div><div className="welcome-tech-name"><TechnologyIcon type="ai"/><strong>AI</strong></div><span>자연어 이해</span></div>
        <div><div className="welcome-tech-name"><TechnologyIcon type="twin"/><strong>Digital Twin</strong></div><span>3D 공간 시각화</span></div>
        <div><div className="welcome-tech-name"><TechnologyIcon type="gis"/><strong>GIS</strong></div><span>도로망 분석</span></div>
      </div>
      <p className="welcome-description" id="welcome-description">원하는 이동 조건을 말로 입력하면,<br/>가로등·CCTV·보행시설과 도로망을 분석해<br/>조건에 맞는 보행 경로를 제안합니다.</p>
      <div className="welcome-condition-grid" role="list" aria-label="경로 분석 항목">
        {CONDITION_ORDER.map((factor) => <span className="welcome-condition-card" role="listitem" key={factor}>
          <ConditionIcon factor={factor}/><span>{CONDITION_LABELS[factor]}</span>
        </span>)}
      </div>
      <footer className="welcome-footer">
        <div className="welcome-agencies" aria-label="사용한 데이터의 출처 기관">
          <div className="welcome-agency-row">
            <img src="/branding/kma.png" alt="기상청"/><img src="/branding/molit.png" alt="국토교통부"/>
            <img src="/branding/incheon.png" alt="인천광역시"/><img src="/branding/michuhol-color.png" alt="미추홀구"/>
            <span className="welcome-osm"><img src="/branding/osm.png" alt=""/>OpenStreetMap</span>
            <img src="/branding/police.png" alt="경찰청"/>
            <span className="welcome-fire"><span className="welcome-fire-symbol"><img src="/branding/nfa.jpg" alt=""/></span>소방청</span>
          </div>
        </div>
        <p className="welcome-creators">김태인 사원 · 김진성 사원</p>
      </footer>
    </dialog>;
}
