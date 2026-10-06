-- Daily kanji wisdom quote: the backend-owned list the Deck and web frontend show one entry of per day.
-- Seeded with the same 30 entries as the Deck's built-in fallback list (KanjiWisdom.kt); edit via
-- /api/kanji. `enabled` rows form the rotation, ordered by id.
CREATE TABLE IF NOT EXISTS `kanji_wisdom` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `kanji` VARCHAR(64) NOT NULL,
  `reading` VARCHAR(128) NOT NULL,
  `meaning` VARCHAR(160) NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_kanji_wisdom_kanji` (`kanji`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `kanji_wisdom` (`kanji`, `reading`, `meaning`) VALUES
  ('独り占め', 'hitorijime', 'keeping something all to oneself'),
  ('七転八起', 'nanakorobi yaoki', 'fall seven times, rise eight'),
  ('一期一会', 'ichigo ichie', 'one lifetime, one meeting: treasure it'),
  ('猿も木から落ちる', 'saru mo ki kara ochiru', 'even monkeys fall from trees'),
  ('石の上にも三年', 'ishi no ue ni mo sannen', 'three years on a stone: persevere'),
  ('継続は力なり', 'keizoku wa chikara nari', 'continuing is power'),
  ('初心忘るべからず', 'shoshin wasuru bekarazu', 'never forget your beginner''s mind'),
  ('急がば回れ', 'isogaba maware', 'in a hurry? take the long way round'),
  ('十人十色', 'juunin toiro', 'ten people, ten colors: all differ'),
  ('以心伝心', 'ishin denshin', 'understanding without words'),
  ('温故知新', 'onko chishin', 'study the old to learn the new'),
  ('自業自得', 'jigou jitoku', 'you reap what you sow'),
  ('一石二鳥', 'isseki nichou', 'one stone, two birds'),
  ('臥薪嘗胆', 'gashin shoutan', 'endure hardship to reach a goal'),
  ('不撓不屈', 'futou fukutsu', 'unbending, unyielding'),
  ('百聞は一見に如かず', 'hyakubun wa ikken ni shikazu', 'seeing once beats hearing 100 times'),
  ('塵も積もれば山となる', 'chiri mo tsumoreba yama to naru', 'even dust, piled up, becomes a mountain'),
  ('時は金なり', 'toki wa kane nari', 'time is money'),
  ('雨降って地固まる', 'ame futte ji katamaru', 'after rain, the ground hardens'),
  ('沈黙は金', 'chinmoku wa kin', 'silence is golden'),
  ('明鏡止水', 'meikyou shisui', 'clear mirror, still water: a calm mind'),
  ('縁の下の力持ち', 'en no shita no chikaramochi', 'the unsung strongman beneath the veranda'),
  ('光陰矢の如し', 'kouin ya no gotoshi', 'time flies like an arrow'),
  ('千里の道も一歩から', 'senri no michi mo ippo kara', 'a journey of 1000 miles: one step first'),
  ('木漏れ日', 'komorebi', 'sunlight filtering through trees'),
  ('侘寂', 'wabi-sabi', 'beauty in imperfection and impermanence'),
  ('初志貫徹', 'shoshi kantetsu', 'see your original resolve through'),
  ('守破離', 'shu-ha-ri', 'obey, break, leave: stages of mastery'),
  ('一日一善', 'ichinichi ichizen', 'one good deed a day'),
  ('花鳥風月', 'kachou fuugetsu', 'flowers, birds, wind, moon: nature''s beauty');
