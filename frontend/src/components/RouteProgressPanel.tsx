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
      <h2>{stage === "done" ? "이렇게 길을 찾았어요" : stage === "failed" ? "경로 검색을 마치지 못했어요" : "길을 찾고 있어요"}</h2>
      <div className="route-progress-log" role="log" aria-live="polite" aria-relevant="additions text">
        {messages.map((message) => (
          <p key={message.id} className={`route-progress-message${message.pending ? " route-progress-message--pending" : ""}`}>
            <span className="route-progress-avatar" aria-hidden="true">↗</span>
            <span>{message.text}{message.pending && <span className="route-progress-dots" aria-hidden="true">···</span>}</span>
          </p>
        ))}
      </div>
    </section>
  );
}
