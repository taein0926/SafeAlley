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
            <span className={`route-progress-avatar${message.pending ? " route-progress-avatar--speaking" : ""}`} aria-hidden="true">
              <svg className="route-progress-lips" viewBox="0 0 32 24" fill="none">
                <path className="route-progress-lip-outline" d="M2 12C6 9 8 4 12 7L16 9L20 7C24 4 26 9 30 12C25 22 7 22 2 12Z" fill="#ed7080" stroke="#ac405e" strokeWidth="1.2" strokeLinejoin="round" />
                <ellipse className="route-progress-mouth" cx="16" cy="12.5" rx="10" ry="3.2" fill="#4c2538" />
                <path d="M8 9.5L12 8.5L16 10" stroke="#ffdce2" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
            </span>
            <span>{message.text}</span>
          </p>
        ))}
      </div>
    </section>
  );
}
