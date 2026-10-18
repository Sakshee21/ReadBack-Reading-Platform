// Small, bundled word data for the word ladder and anagram variants. This is
// deliberately not a full dictionary: a ladder step must be one of WORDS.

const RAW = `
bake bale ball band bane bank bare bark barn base bash bath bead beam bean bear beat beef been beer
bell belt bend bent best bile bill bind bird bite blow blue boar boat body boil bold bolt bone book
boot bore born boss both bowl burn bush busy cage cake call calm came camp cane cape card care cart
case cash cast cave cell cent chat chip city clam clap clay clip club coal coat code coil coin cold
comb come cook cool cope cord core corn cost cove crew crop cure curl dale dame damp dare dark dart
dash data date dawn deal dear deck deed deep deer dent desk dial dice diet dime dine dirt dish dive
dock dole doll dome done door dose dove down drag draw drew drip drop drum duck dull dune dusk dust
duty each earn ease east easy edge even ever face fact fade fail fair fake fall fame fare farm fast
fate fear feed feel feet fell felt fern file fill film find fine fire firm fish fist five flag flat
flew flip flow foam fold folk fond food fool foot ford fore fork form fort foul four free from fuel
full fund gain gale game gate gave gear gift girl give glad glow glue goal goat gold golf gone good
gown grab gray grew grid grin grip grow gulf hail hair half hall hand hang hard hare harm hate haul
have hawk head heal heap hear heat held help hemp herb here hero hide high hill hint hire hold hole
holy home hood hook hope horn host hour huge hunt hurt idea inch iron item jail join joke jump junk
just keen keep kept kick kind king kiss kite knee knew knit knot know lace lack lady laid lake lamb
lame lamp land lane last late lawn lazy lead leaf lean leap left lend lens less lick life lift like
limb lime line link lion list live load loaf loan lock loft lone long look loop lord lose loss lost
loud love luck lump made mail main make male mall mane many mare mark mask mass mast mate maze meal
mean meat meet melt menu mild mile milk mill mind mine mint miss mist mode mole moon more moss most
moth move much mule must nail name navy near neat neck need nest news next nice nine node none noon
nose note oath obey once only open oven over pace pack page paid pain pair pale palm park part pass
past path pawn peak pear peel peer pick pier pile pill pine pink pipe plan play plot plug plus poem
pole poll pond pool poor pork port pose post pour pray pull pump pure push race rack rage raid rail
rain rake rank rare rate read real rear rent rest rice rich ride ring rise risk road roar robe rock
rode role roll roof room root rope rose rude rule rush rust safe said sail sake sale salt same sand
sang save seal seat seed seek seem seen self sell send sent shed ship shoe shop shot show shut sick
side sign silk sing sink site size skin skip slid slim slip slow snap snow soak soap sock soft soil
sold sole some song soon sore sort soul soup sour span spin spot star stay stem step stir stop suit
sung sure swim tail take tale talk tall tank tape task team tear tell tend tent term test text than
that then thin this tick tide tidy tied tile till time tiny tire toad told toll tone took tool tore
torn tour town trap tray tree trim trip true tube tuck tune turn twin type unit upon urge used vain
vase vast very vest view vine void vote wade wage wait wake walk wall want ward warm warn wash wave
weak wear weed week well went were west what when wide wife wild will wind wine wing wipe wire wise
wish with wolf wood wool word wore work worm worn wrap yard yarn year zero zone
`;

// More everyday words, so common guesses such as "mold" or "back" are accepted.
const EXTRA = `
back bail bait bike blot blur boom brim buck bulb bulk bull bump buzz cafe calf chew chin chop clue
crab crow cube cuff cute dock dorm doze drab dump dyed echo edit emit envy epic exam exit fang fend
fizz flap flee flex flop flux fray fret frog fume funk fury fuse gaze gems glee glib glum gnat gram
grim grub gush gust hack halt heck heel hike hips hiss hive hoax hulk hush hymn icon iffy isle jade
jams jaws jeep jest jinx jobs jogs jolt joys judo jugs keys kids kiln kits lags lava lays lids lisp
loom lore lush lynx maid mash maul mend mesh mice mock moan mold mood moor mope muck mugs muse mute
myth nags naps newt nick nips nook norm nuns nuts oats odor ogle oils omit ooze orbs ores owed owls
owns pads paws pegs pens perk pest pets pigs pins pits plea plod plow ploy pods pomp pops posh pots
prod prop pubs pulp punt purr quit raft rags rams rant raps rash rays reed reef rely ribs rift rims
rink rips roam robs rods romp rots rows rubs ruby rugs rung runs ruts sack sage sags scab scan scar
seam seep sews shim shin shun silo sill sips sire skid skit slab slag slat slay slot slug slum smog
smug snag snub soar sobs sofa soot spam spar spat sped spit spud spur stab stag stub stud stun suds
sulk surf swan swap sway swat tabs tack tags tame tang taps tart taut teak teen tens tern thaw thud
tics tins tips toes toga toil tomb tops toss tote tots tout tows toys tram trek trio trod tuba tubs
tuft tugs tuna turf tusk twig undo unto uses vale vary veal veer veil vein vent verb vets vibe vice
vile visa vole wads wand wane wart wary wasp wavy waxy ways weld whim whip wick wilt wink wits woes
woke womb wove wren yawn yelp yoga yolk your zeal zinc zips zoom
`;

// Words that are real but too obscure to expect from a casual player.
const OBSCURE = new Set(["bane", "dole", "cove", "hemp", "bile", "wade"]);

const oneApart = (a, b) => a.length === b.length && [...a].filter((c, i) => c !== b[i]).length === 1;

const CANDIDATES = [...new Set((RAW + " " + EXTRA).split(/\s+/).filter(Boolean))].filter(
  (w) => !OBSCURE.has(w)
);

// A word with no one-letter neighbour could never be part of a ladder, so it
// would only ever be rejected as "not a word"; leave it out.
export const WORDS = CANDIDATES.filter((w) => CANDIDATES.some((o) => oneApart(w, o)));

// Each pair has a shortest path of 3 or 4 steps through WORDS (checked by tests).
export const LADDERS = [
  { start: "cold", target: "hard" },
  { start: "head", target: "team" },
  { start: "love", target: "cake" },
  { start: "soap", target: "rock" },
  { start: "bird", target: "land" },
  { start: "door", target: "four" },
  { start: "wood", target: "cold" },
  { start: "fish", target: "cash" },
  { start: "cold", target: "coat" },
  { start: "sand", target: "cake" },
  { start: "love", target: "page" },
  { start: "wall", target: "bank" },
];

// Common 5-letter words with no second listed arrangement of the same letters.
export const ANAGRAMS = [
  "quilt", "music", "money", "tiger", "river", "storm", "bench", "flute", "brick", "chair",
  "apple", "berry", "zebra", "knife", "pilot", "robin", "candy", "thumb", "wheat", "lunch",
  "light", "crowd", "trunk", "blind", "clock", "sweet", "jelly", "grain",
];
