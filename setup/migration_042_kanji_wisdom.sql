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
  ('ヒトリジメ', 'hitorijime', 'keeping something all to oneself'),
  ('ナナコロビヤオキ', 'nanakorobi yaoki', 'fall seven times, rise eight'),
  ('イチゴイチエ', 'ichigo ichie', 'one lifetime, one meeting: treasure it'),
  ('サルモキカラオチル', 'saru mo ki kara ochiru', 'even monkeys fall from trees'),
  ('イシノウエニモサンネン', 'ishi no ue ni mo sannen', 'three years on a stone: persevere'),
  ('ケイゾクワチカラナリ', 'keizoku wa chikara nari', 'continuing is power'),
  ('ショシンワスルベカラズ', 'shoshin wasuru bekarazu', 'never forget your beginner''s mind'),
  ('イソガバマワレ', 'isogaba maware', 'in a hurry? take the long way round'),
  ('ジュウニントイロ', 'juunin toiro', 'ten people, ten colors: all differ'),
  ('イシンデンシン', 'ishin denshin', 'understanding without words'),
  ('オンコチシン', 'onko chishin', 'study the old to learn the new'),
  ('ジゴウジトク', 'jigou jitoku', 'you reap what you sow'),
  ('イッセキニチョウ', 'isseki nichou', 'one stone, two birds'),
  ('ガシンショウタン', 'gashin shoutan', 'endure hardship to reach a goal'),
  ('フトウフクツ', 'futou fukutsu', 'unbending, unyielding'),
  ('ヒャクブンワイッケンニシカズ', 'hyakubun wa ikken ni shikazu', 'seeing once beats hearing 100 times'),
  ('チリモツモレバヤマトナル', 'chiri mo tsumoreba yama to naru', 'even dust, piled up, becomes a mountain'),
  ('トキワカネナリ', 'toki wa kane nari', 'time is money'),
  ('アメフッテジカタマル', 'ame futte ji katamaru', 'after rain, the ground hardens'),
  ('チンモクワキン', 'chinmoku wa kin', 'silence is golden'),
  ('メイキョウシスイ', 'meikyou shisui', 'clear mirror, still water: a calm mind'),
  ('エンノシタノチカラモチ', 'en no shita no chikaramochi', 'the unsung strongman beneath the veranda'),
  ('コウインヤノゴトシ', 'kouin ya no gotoshi', 'time flies like an arrow'),
  ('センリノミチモイッポカラ', 'senri no michi mo ippo kara', 'a journey of 1000 miles: one step first'),
  ('コモレビ', 'komorebi', 'sunlight filtering through trees'),
  ('ワビサビ', 'wabi-sabi', 'beauty in imperfection and impermanence'),
  ('ショシカンテツ', 'shoshi kantetsu', 'see your original resolve through'),
  ('シュハリ', 'shu-ha-ri', 'obey, break, leave: stages of mastery'),
  ('イチニチイチゼン', 'ichinichi ichizen', 'one good deed a day'),
  ('カチョウフウゲツ', 'kachou fuugetsu', 'flowers, birds, wind, moon: nature''s beauty');
