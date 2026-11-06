import {
  Box,
  CarFront,
  Castle,
  Clapperboard,
  Code,
  Cog,
  Compass,
  FlaskConical,
  Gift,
  GraduationCap,
  ImageIcon,
  type LucideIcon,
  Palette,
  Puzzle,
  ScrollText,
  Sparkles,
  Swords,
  Tag,
  Users,
  Volleyball,
  Wrench,
} from "lucide-react";

/**
 * 장르 아이콘(화면 장식). 서버가 내보내는 한국어 장르명(backend/app/genre_labels.py) 기준이고,
 * 표에 없는 장르(영어 그대로 오는 것 포함)는 태그 아이콘.
 */
const GENRE_ICON: Record<string, LucideIcon> = {
  액션: Swords,
  인디: Sparkles,
  어드벤처: Compass,
  시뮬레이션: Cog,
  RPG: ScrollText,
  전략: Castle,
  캐주얼: Puzzle,
  "무료 플레이": Gift,
  "대규모 멀티플레이어": Users,
  스포츠: Volleyball,
  "앞서 해보기": FlaskConical,
  레이싱: CarFront,
  유틸리티: Wrench,
  "애니메이션과 모델링": Box,
  "디자인과 일러스트레이션": Palette,
  "동영상 제작": Clapperboard,
  "소프트웨어 교육": GraduationCap,
  "사진 편집": ImageIcon,
  "게임 개발": Code,
};

export function genreIcon(genre: string): LucideIcon {
  return GENRE_ICON[genre] ?? Tag;
}
