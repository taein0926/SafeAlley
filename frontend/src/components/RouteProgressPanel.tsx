import type { RouteQueryResponse } from "../types";
import { progressMessages } from "../routeProgress";
import type { RouteWorkUpdate } from "../routeProgress";

type Props = {
  stage: "interpreting" | "resolving" | "routing" | "done" | "failed";
  interpretation: RouteQueryResponse["interpretation"] | null;
  originName: string | null;
  destinationName: string | null;
  result: RouteQueryResponse["result"] | null;
  workUpdates: RouteWorkUpdate[];
};

export function RouteProgressPanel({ stage, interpretation, originName, destinationName, result, workUpdates }: Props) {
  const messages = progressMessages(stage, interpretation, originName, destinationName, result, workUpdates);

  return (
    <section className="route-progress" aria-label="경로 검색 처리 과정">
      <h2>{stage === "failed" ? "경로 검색을 마치지 못했어요" : "AI가 길을 찾고 있어요"}</h2>
      <div className="route-progress-log" role="log" aria-live="polite" aria-relevant="additions text">
        {messages.map((message) => (
          <p key={message.id} className={`route-progress-message${message.pending ? " route-progress-message--pending" : ""}`}>
            <span className={`route-progress-avatar${message.pending ? " route-progress-avatar--thinking" : stage === "failed" ? " route-progress-avatar--waiting" : " route-progress-avatar--complete"}`} aria-hidden="true">
              {message.pending ? (
                <svg className="route-progress-robot" viewBox="0 0 42 38" fill="none">
                  <g className="route-progress-robot-head">
                    <path d="M20 13V9M6 20v7M34 20v7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <circle className="route-progress-robot-antenna" cx="20" cy="6.5" r="2.5" fill="currentColor" />
                    <rect x="8" y="13" width="24" height="20" rx="6" fill="white" stroke="currentColor" strokeWidth="1.7" />
                    <g className="route-progress-robot-eyes" fill="currentColor">
                      <rect x="13" y="19" width="4" height="5" rx="2" />
                      <rect x="23" y="19" width="4" height="5" rx="2" />
                    </g>
                    <path d="M15 28q5 3 10 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  </g>
                  <rect x="27" y="1" width="14" height="8" rx="4" fill="white" stroke="currentColor" strokeWidth="1" />
                  {[30, 34, 38].map((cx, index) => <circle key={cx} className="route-progress-thought-dot" cx={cx} cy="5" r="1" fill="currentColor" style={{ animationDelay: `${index * 0.18}s` }} />)}
                </svg>
              ) : (
                <svg className={stage === "failed" ? "route-progress-waiting" : "route-progress-check"} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <path d={stage === "failed" ? "M12 6v8M12 18h.01" : "m5 12 4 4L19 6"} />
                </svg>
              )}
            </span>
            <span>{message.text}</span>
          </p>
        ))}
      </div>
    </section>
  );
}
