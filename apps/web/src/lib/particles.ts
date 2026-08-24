/**
 * 한국어 조사 선택.
 *
 * 화면 문구에 단어를 끼워 넣을 때 조사를 고정하면 반드시 한쪽이 틀립니다
 * ("부스는" ○ / "부스은" ✗, "미션은" ○ / "미션는" ✗). 실제로 세 번 틀렸습니다.
 *
 * 백엔드에도 같은 판단이 필요해 `core/errors.py` 에 짝이 되는 함수가 있습니다.
 * 규칙은 같습니다 — 한글 음절의 종성 유무로 고르고, 한글이 아닌 글자로 끝나면
 * 읽는 방식이 갈리므로 받침 없는 쪽을 씁니다.
 */

function hasFinalConsonant(word: string): boolean | null {
  if (!word) return null;
  const last = word[word.length - 1];
  const code = last.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return null; // 한글 음절이 아님
  return (code - 0xac00) % 28 !== 0;
}

const pick = (word: string, withFinal: string, without: string) =>
  hasFinalConsonant(word) === true ? withFinal : without;

/** 주격 — 부스**가** / 미션**이** */
export const subject = (word: string) => pick(word, '이', '가');

/** 보조사 — 부스**는** / 미션**은** */
export const topic = (word: string) => pick(word, '은', '는');

/** 목적격 — 축제**를** / 진단**을** */
export const object = (word: string) => pick(word, '을', '를');
