import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage.settings_manager import get_master_presets_registry_path

registry_path = get_master_presets_registry_path()
if not registry_path:
    print("ERROR: master_presets_registry.json not found.")
    sys.exit(1)
registry = json.loads(registry_path.read_text(encoding="utf-8"))

NEW_PRESETS = {
    "ink_explainer": {
        "preset_name": "ink_explainer",
        "display_name": "Ink Explainer",
        "description": "Atmospheric anthropological deep dives, prehistoric human evolution, survival psychology, and the ancient origins of human nature.",
        "voice_name": "Michael·  American Male",
        "video_language": "English",
        "content_automation": {
            "title_structure": "What Did Ancient Humans Actually [Fear/Do/Believe]? (The Disturbing Truth Behind [Trait/Behavior])",
            "hook_style": "Immediate anthropological cognitive dissonance. Subverting modern assumptions with a visceral primal survival dilemma.",
            "target_words": 1900,
            "target_duration_minutes": 10,
            "tone": "Atmospheric, contemplative, scientific, immersive anthropological storytelling with deep philosophical curiosity.",
            "pacing": "Measured, rhythmic momentum, 160-175 wpm, alternating between intense survival anecdotes and evolutionary insights.",
            "scene_density": "1 visual scene every 3-4 sentences",
            "narrative_structure": "Chapter-based anthropological journey (5-7 chapters): Chapter 1: The Modern Illusion (The Counterintuitive Hook & Everyday Enigma) -> Chapter 2: The Primal Dawn (Ice Age Conditions & Evolutionary Baseline) -> Chapter 3: The Survival Catalyst (The Crisis, Hunt, Or Chemical Discovery) -> Chapter 4: The Neurological Imprint (How The Brain Adapted To Fear & Community) -> Chapter 5: The Lost Cousins (Neanderthal Encounters & Extinction Mysteries) -> Chapter 6: The Modern Echo (Why We Still Carry The Pleistocene Mind In The Digital Age)",
            "chapter_format": "[Chapter: <Title>]"
        },
        "image_automation": {
            "visual_style": "atmospheric primal anthropological tableau, textured charcoal and sumi-ink brushwork on dark slate rock canvas, primal campfire amber glow casting dramatic long shadows, deep earthy ochre, bone-white highlights, drifting smoke and glowing ember particles, gritty cinematic framing, evocative prehistoric realism",
            "aspect_ratio": "16:9",
            "negative_prompt": "bright neon colors, cartoon, flat 2d vector, anime, plastic 3d CGI, modern clothes, modern buildings, modern technology, oversaturated colors, text, watermark, blurry faces",
            "model": "Imagen 3",
            "generation_mode": "image",
            "character_consistency": "Weathered, authentic prehistoric Homo sapiens with expressive observant eyes, coarse natural fur/hide clothing, firelit skin tones, and intense primal focus.",
            "environment_consistency": "Deep limestone cave interiors with flickering torchlight, mist-covered glacial valleys, nocturnal Pleistocene savannah under vast starry skies, smoldering hearth stones.",
            "cinematic_style": "Cinematic anthropological documentary, intimate low-angle torchlight close-ups, wide atmospheric glacial landscape vistas, deep chiaroscuro contrast."
        },
        "video_forge": {
            "allowed_transitions": ["dissolve", "fade", "smoothleft", "smoothright", "radial"],
            "video_styling": "Atmospheric primal anthropological storytelling with slow macro drifts",
            "sub_mode": "karaoke",
            "sub_position": "bottom_center",
            "subtitle_font": "Georgia",
            "subtitle_font_size": 52,
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_spacing": 0.8,
            "subtitle_uppercase": False,
            "subtitle_primary_color": "&H00DDEEF4",
            "subtitle_karaoke_color": "&H0028A0FF",
            "subtitle_karaoke_outline": "&H000F151C",
            "subtitle_outline_color": "&H0015181C",
            "subtitle_back_color": "&HA00D1014",
            "subtitle_outline_width": 2.8,
            "subtitle_shadow": 1.8,
            "subtitle_border_style": 1,
            "subtitle_alignment": 2,
            "subtitle_animation": "glow",
            "subtitle_margin_v": 65,
            "subtitle_max_chars": 36
        },
        "niche_topics": [
            "What Did Ancient Humans Actually Fear? (It Was Not Predators)",
            "Why Humans Are The Only Mammal That Can Run For 24 Hours Straight",
            "When Did Ancient Humans Start Drinking Alcohol (And Why It Built Civilization)?",
            "The Terrifying Ways Prehistoric Humans Survived Ice Age Winters",
            "What Did Ancient Humans Actually Do When It Rained For Weeks?",
            "Why Neanderthals Had Larger Brains Than Us But Still Disappeared",
            "The Disturbing Evolutionary Reason Why Humans Experience Loneliness",
            "When Did Humans First Realize That Sex Causes Babies?",
            "What Ancient Humans Ate On An Average Tuesday 50,000 Years Ago",
            "Why Humans Started Cooking Food (And How It Shrunk Our Guts)",
            "The Dark Origins Of Human Monogamy And Tribal Warfare",
            "How Early Humans Hunted The Deadliest Beasts With Just Sharp Sticks",
            "Why Ancient Humans Painted In Pitch-Black Caves Miles Underground",
            "The First Human Who Discovered Fire: How An Accident Changed Biology",
            "Why Humans Are The Only Animal That Blushes And Weeps",
            "What Prehistoric Humans Did For Fun Before Language Existed",
            "The 70,000-Year-Old Genetic Bottleneck That Almost Wiped Out Humanity",
            "Why Ancient Humans Feared The Dark More Than Anything Else",
            "How Hunter-Gatherers Slept: The Truth About Biphasic Sleep",
            "The Bizarre Rituals Ancient Humans Used To Explain Death"
        ],
        "thumbnail_styles": [
            {
                "id": "primal_predator_firelight",
                "name": "The Primal Stare In The Ember Glow",
                "description": "Ultra-dramatic prehistoric human face occupying 50% of the frame illuminated by fierce flickering campfire light, dilated pupils reflecting a looming towering saber-toothed beast silhouette in the pitch-black cave entrance, glowing orange ember particles drifting, deep charcoal slate background, high tension, no text."
            },
            {
                "id": "mammoth_abyss_hunt",
                "name": "The Edge Of The Glacial Abyss",
                "description": "Lone prehistoric hunter silhouetted against a gigantic woolly mammoth skull buried in glacial ice, glowing torch held high casting long dynamic shadows across fractured permafrost, dark moody atmospheric blizzard haze, extreme scale contrast, no text."
            },
            {
                "id": "first_spark_discovery",
                "name": "The First Spark",
                "description": "Extreme macro close-up of two rough flint stones striking together, freezing a brilliant blinding white-hot spark erupting between weathered dirt-stained prehistoric hands, deep obsidian cave shadows, sudden dramatic illumination, intense curiosity, no text."
            }
        ],
        "offline_voice": "Michael·  American Male",
        "elevenlabs_voice": "George - Warm, Captivating Storyteller  ·  ElevenLabs (Male)",
        "voices": {
            "offline": "Michael·  American Male",
            "elevenlabs": "George - Warm, Captivating Storyteller  ·  ElevenLabs (Male)"
        }
    },
    "built_on_you": {
        "preset_name": "built_on_you",
        "display_name": "Built On You",
        "description": "Cinematic chronological corporate documentaries, founder origin epics, high-stakes boardroom gambles, and business empire histories.",
        "voice_name": "Adam   ·  American Male",
        "video_language": "English",
        "content_automation": {
            "title_structure": "The ENTIRE History of [Brand/Empire]: From [Humble Garage/Crisis] to [Trillion-Dollar Giant/Collapse]",
            "hook_style": "Definitive chronological scope promise paired with an extreme high-stakes founder near-death bankruptcy dilemma.",
            "target_words": 2200,
            "target_duration_minutes": 12,
            "tone": "Authoritative, investigative, cinematic, balanced corporate journalism, dramatic tension without hype.",
            "pacing": "Steadily accelerating momentum, 165-180 wpm, layered narrative rhythm with pivotal financial turning points.",
            "scene_density": "1 visual scene every 3-4 sentences",
            "narrative_structure": "Chapter-based corporate empire arc (6-7 chapters): Chapter 1: The Outlier Origin (The Garage Genesis & The Absurd Gamble) -> Chapter 2: The Breakthrough Disruption (Cracking The Market & The First Millions) -> Chapter 3: The Brink Of Bankruptcy (The Bet-The-Company Crisis & Executive Bloodbath) -> Chapter 4: The Ruthless Counter-Offensive (Crushing Rivals & The Monopoly Strategy) -> Chapter 5: The Golden Era Of Dominance (Wall Street Triumph & Cultural Empire) -> Chapter 6: The Modern Scandal & Reckoning (Regulatory Crosshairs & Succession Dilemma) -> Chapter 7: The Lasting Doctrine (The Management Principles That Built The Empire)",
            "chapter_format": "[Chapter: <Title>]"
        },
        "image_automation": {
            "visual_style": "cinematic archival corporate documentary collage, 2.5D multi-plane parallax depth, aged executive patent schematics, vintage typewriter typography, textured newspaper grain, rich executive mahogany and deep forest green palette, subtle film burn light leaks, high-contrast monochrome founder portraits with golden duotone highlights",
            "aspect_ratio": "16:9",
            "negative_prompt": "bright cartoon, anime, low-fi vector, plastic 3d toy render, messy chaotic composition, unreadable text artifacts, watermark, low quality, oversaturated rainbows",
            "model": "Imagen 3",
            "generation_mode": "image",
            "character_consistency": "Sharp, era-accurate iconic business founders and visionary CEOs in vintage bespoke suits, rolled-up shirtsleeves in gritty workrooms, intense calculated expressions.",
            "environment_consistency": "Smoky 1970s wood-paneled executive boardrooms, cluttered suburban garages with CRT monitors and cardboard boxes, gleaming modern glass skyscraper atriums at dusk.",
            "cinematic_style": "Archival multi-plane documentary cinematography, slow dramatic 3D parallax glides over vintage contracts, intimate low-key executive portraiture."
        },
        "video_forge": {
            "allowed_transitions": ["fade", "dissolve", "horzopen", "vertopen", "smoothright"],
            "video_styling": "Cinematic archival corporate documentary with 2.5D multi-plane parallax",
            "sub_mode": "karaoke",
            "sub_position": "bottom_center",
            "subtitle_font": "Franklin Gothic Medium",
            "subtitle_font_size": 54,
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_spacing": 1.0,
            "subtitle_uppercase": False,
            "subtitle_primary_color": "&H00F6F9F9",
            "subtitle_karaoke_color": "&H003BB8E5",
            "subtitle_karaoke_outline": "&H00101418",
            "subtitle_outline_color": "&H00181412",
            "subtitle_back_color": "&H90100D0C",
            "subtitle_outline_width": 3.0,
            "subtitle_shadow": 1.8,
            "subtitle_border_style": 1,
            "subtitle_alignment": 2,
            "subtitle_animation": "pop",
            "subtitle_margin_v": 68,
            "subtitle_max_chars": 36
        },
        "niche_topics": [
            "The ENTIRE History of Amazon: From Garage Bookseller To $2 Trillion Empire",
            "The ENTIRE History of Nintendo: From 1889 Yakuza Playing Cards To Global Gaming Titan",
            "How Walmarts Founder Destroyed Small-Town Retail and Built a Retail Monolith",
            "The ENTIRE History of Microsoft: The 1980 IBM Deal That Changed Computing Forever",
            "How Toyota Out-Manufactured Detroit and Created The Worlds Most Reliable Cars",
            "The Ruthless Rise of Nike: How Phil Knight Smuggled Japanese Shoes From His Car Trunk",
            "The ENTIRE History of Apple: From Steves Cupertino Garage To $3 Trillion Tech Sovereign",
            "How Ferrari Beat Ford In Racing Lore: The Feud That Built A Supercar Legend",
            "The Collapse and Resurrection of Lego: How The Danish Brick Nearly Vanished in 2003",
            "How Sony Invented The Walkman, Conquered Pop Culture, and Lost The Digital Age",
            "The ENTIRE History of Boeing: From Alaskan Spruce Biplanes To Commercial Aviation Giant",
            "How McDonalds Turned Cheap Hamburgers Into A Global Real Estate Empire",
            "The Untold Story of Rolex: How Hans Wilsdorf Created The Ultimate Luxury Status Symbol",
            "The ENTIRE History of Intel: The Silicon Valley Pioneers Who Power The Worlds Chips",
            "How Ikea Conquered Flat-Pack Furniture And Created A Global Design Cult",
            "The Rise, Fall, and Rebirth of Marvel: From 1996 Bankruptcy To Cinema Dominance",
            "How Red Bull Created An Extreme Sports Empire Out Of A Thai Trucker Tonic",
            "The ENTIRE History of Porsche: Ferdinands Engineering Legacy And The 911 Icon",
            "How Netflix Crushed Blockbuster And Upended Hollywoods 100-Year Movie Monopoly",
            "The ENTIRE History of SpaceX: How Elon Musk Bet His Last $30 Million On Falcon 1"
        ],
        "thumbnail_styles": [
            {
                "id": "garage_to_skyscrapers_split",
                "name": "The Garage vs. Empire Parallax",
                "description": "High-contrast archival collage: left side shows a gritty black-and-white 1970s suburban garage with a lone wooden desk and cluttered cardboard boxes; right side seamlessly bursts into a towering modern glass skyscraper illuminated by golden executive boardroom light, layered vintage patent schematics floating in mid-air, no text."
            },
            {
                "id": "the_bankruptcy_brink",
                "name": "The $0 Balance Sheet",
                "description": "A dramatic high-angle view of a solitary founder in an empty corporate hallway late at night, surrounded by towering stacks of eviction notices and ledger books, dramatic down-light casting an ominous elongated shadow toward a single glowing boardroom door, deep mahogany and dark navy tones, no text."
            },
            {
                "id": "the_monopoly_architect",
                "name": "The Architects War Room",
                "description": "Close-up of a resolute visionary founder standing over a massive mahogany table covered in overlapping global logistical maps with gold pins and red supply chain vectors, hands planted firmly, warm vintage executive chiaroscuro lighting, no text."
            }
        ],
        "offline_voice": "Adam   ·  American Male",
        "elevenlabs_voice": "Jonathan - Professional, Calm, Credible, Clear  ·  ElevenLabs (Male)",
        "voices": {
            "offline": "Adam   ·  American Male",
            "elevenlabs": "Jonathan - Professional, Calm, Credible, Clear  ·  ElevenLabs (Male)"
        }
    },
    "terrain_walk": {
        "preset_name": "terrain_walk",
        "display_name": "Terrain Walk",
        "description": "Tactical military battle breakdowns, 3D digital elevation models, line-of-sight topographical analysis, and ground-level infantry/tank maneuver geometry.",
        "voice_name": "Adam   ·  American Male",
        "video_language": "English",
        "content_automation": {
            "title_structure": "How [Small Force/Tanks] Beat [Overwhelming Numbers] In [Sandstorm/Fog/Chokepoint]: The Battle of [Engagement]",
            "hook_style": "Immediate tactical crisis on the ground. A tiny force is hopelessly outgunned until the terrain geometry shifts the equation.",
            "target_words": 2000,
            "target_duration_minutes": 11,
            "tone": "Crisp, clinical, authoritative military tactical analysis, intense battlefield momentum, zero sensationalism.",
            "pacing": "Punchy, calculated, rhythmic delivery, 165-180 wpm, synchronizing perfectly with tactical elevation reveals.",
            "scene_density": "1 visual scene every 3 sentences",
            "narrative_structure": "Chapter-based tactical ground breakdown (5-7 chapters): Chapter 1: The Disadvantage (Outnumbered In The Killing Zone) -> Chapter 2: The Topographical Terrain (Reading The Ridges, Reverse Slopes & Dead Space) -> Chapter 3: The Environmental Cloak (Fog, Sandstorm & Blind Armor Sights) -> Chapter 4: The Opening Volley & Flank Breach (Exploiting The Elevation Advantage) -> Chapter 5: The Armor Clash (Knife-Fight Range In The Ravine) -> Chapter 6: The Decisive Maneuver (Cutting The Withdrawal Route & Overrun) -> Chapter 7: The After-Action Review (Why Topography Trumps Numerical Superiority)",
            "chapter_format": "[Chapter: <Title>]"
        },
        "image_automation": {
            "visual_style": "high-precision 3D digital elevation model terrain visualization, photorealistic satellite relief topography, glowing contour elevation lines, tactical NATO unit military symbols, glowing range rings, line-of-sight elevation cones, dynamic thermal weather overlays, military grid coordinates, dark tactical command aesthetics",
            "aspect_ratio": "16:9",
            "negative_prompt": "fantasy magic, cartoon, bright cartoon colors, plastic toy soldiers, blurry elevation, distorted terrain, unreadable text, low resolution",
            "model": "Imagen 3",
            "generation_mode": "image",
            "character_consistency": "Elite armor crewmen, forward observers, and infantry platoon leaders in authentic combat gear with mud-spattered helmets, looking through binoculars or thermal sights.",
            "environment_consistency": "Rugged tactical ridgelines, arid Iraqi desert wadis during orange duststorms, mist-shrouded French bocage hedgerows, snow-covered Ardennes forest passes with tracked mud ruts.",
            "cinematic_style": "Precision military GIS telemetry flyover, sweeping 3D terrain perspective dips into ravines, thermal infrared weapon sight cutaways, crisp topographic clarity."
        },
        "video_forge": {
            "allowed_transitions": ["wipeleft", "wiperight", "circlecrop", "fade", "dissolve"],
            "video_styling": "3D topographical tactical military visualization with elevation tracking",
            "sub_mode": "karaoke",
            "sub_position": "bottom_center",
            "subtitle_font": "Consolas",
            "subtitle_font_size": 52,
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_spacing": 1.5,
            "subtitle_uppercase": True,
            "subtitle_primary_color": "&H00E0FFFF",
            "subtitle_karaoke_color": "&H0000E5FF",
            "subtitle_karaoke_outline": "&H00000000",
            "subtitle_outline_color": "&H00000A05",
            "subtitle_back_color": "&HB0000000",
            "subtitle_outline_width": 3.2,
            "subtitle_shadow": 2.0,
            "subtitle_border_style": 1,
            "subtitle_alignment": 2,
            "subtitle_animation": "pop",
            "subtitle_margin_v": 65,
            "subtitle_max_chars": 34
        },
        "niche_topics": [
            "How 9 Tanks Beat 50 In A Sandstorm: The Battle Of 73 Easting (Desert Storm)",
            "How Outgunned Shermans Destroyed 43 German Panthers In Thick Fog (Arracourt 1944)",
            "How 13 Men Neutralized 60 Germans On D-Day: The Real Brecourt Manor Tactical Assault",
            "The Dead Space Ambush At Ia Drang: How LZ X-Ray Survived Total Encirclement",
            "How 300 Spartans Exploited The Narrow Phalanx Chokepoint At Thermopylae",
            "The Reverse Slope Trap At Waterloo: How Wellington Hid 30,000 Men Behind A Ridge",
            "Why The Germans Could Not Cross The Meuse At Sedan: The 1940 River Assault Breakdown",
            "The Ridge Defense At Bloody Ridge: How 800 Marines Held Off 3,000 Japanese At Guadalcanal",
            "How Russian T-34s Swarmed German Tigers At Kursk: The Prokhorovka Terrain Map",
            "The High Ground Catastrophe At Dien Bien Phu: How French Artillery Lost The Valley",
            "The Ardennes Chokepoint Trap: How Bastognes Road Hub Halted Hitlers Winter Offensive",
            "How The British Longbows Used Mud and Wooden Stakes At Agincourt To Defeat Chivalry",
            "The Micro-Terrain Defense At Hamburger Hill: Why Ap Bia Mountain Cost 72 Lives",
            "How General Patton Used Speed And Snow Defiles To Relieve The 101st Airborne",
            "The Ambush At Long Tan: How 108 ANZAC Troops Held Off 2,500 In A Rubber Plantation",
            "Why Market Gardens Single Highway Became A 64-Mile Death Corridor",
            "How The Desert Rats Used Wadi Depressions To Ambush Rommels Panzers At El Alamein",
            "The Urban Chokepoints Of Ortona: How Canadian Troops Invented Mouse-Holing In 1943",
            "How Rommel Exploited The Halfaya Pass Chokepoint With Concealed 88mm Anti-Tank Guns",
            "The Defensive Geometry Of The Bar Lev Line: How Egyptian Sapper Water Cannons Breached It"
        ],
        "thumbnail_styles": [
            {
                "id": "sandstorm_tank_ambush",
                "name": "The Sandstorm Thermal Ambush",
                "description": "High-angle 3D elevation terrain view of a desolate desert ridge during a roaring orange sandstorm; a lone American Abrams tank on the crest locks its glowing thermal green targeting sight onto a cluster of enemy tanks trapped in the low-lying wadi dead space below, contour elevation lines glowing softly, no text."
            },
            {
                "id": "fog_valley_armor_clash",
                "name": "The Arracourt Fog Ridge",
                "description": "3D topographical perspective of a rolling European farmland valley choked in dense morning fog; concealed Sherman tanks positioned in the reverse slope tree line firing down into the exposed flank of heavy German tanks crossing the mud road, smoke plumes rising, no text."
            },
            {
                "id": "dday_bunker_flank_vector",
                "name": "The Trench Line Breaching Angle",
                "description": "Topographical tactical visualization of a sunken hedgerow lane and concrete artillery bunker; glowing tactical squad maneuver arrows showing small fire teams looping around the dead space behind the machine gun embrasure, explosive muzzle flash illuminating the wet earth, no text."
            }
        ],
        "offline_voice": "Adam   ·  American Male",
        "elevenlabs_voice": "Josh   ·  ElevenLabs (Male)",
        "voices": {
            "offline": "Adam   ·  American Male",
            "elevenlabs": "Josh   ·  ElevenLabs (Male)"
        }
    },
    "go_documentaries": {
        "preset_name": "go_documentaries",
        "display_name": "Go Documentaries",
        "description": "Monumental mega-engineering investigations, geopolitical chokepoints, extreme infrastructure marvels, and planetary logistics.",
        "voice_name": "Michael·  American Male",
        "video_language": "English",
        "content_automation": {
            "title_structure": "How [Country/Engineers] [Solved Impossible Problem/Built Wonder] With [Extreme Mega-Engineering] (And Why It Almost Failed)",
            "hook_style": "Monumental engineering paradox: posing an impossible geographic constraint that should violate the laws of physics or logistics.",
            "target_words": 2100,
            "target_duration_minutes": 11,
            "tone": "Cinematic, awe-inspiring, intellectually rigorous, investigative engineering journalism with pristine technical clarity.",
            "pacing": "Grand, deliberate, escalating momentum, 160-175 wpm, alternating between staggering physical scales and micro-engineering breakthroughs.",
            "scene_density": "1 visual scene every 3-4 sentences",
            "narrative_structure": "Chapter-based mega-engineering arc (6 chapters): Chapter 1: The Impossible Geography (The Planetary Chokepoint Or Arid Crisis) -> Chapter 2: The Radical Blueprint (The Unorthodox Engineering Scheme That Defied Conventional Wisdom) -> Chapter 3: The Subterranean / Marine Battle (Taming Ocean Pressures, Desert Heat & Shifting Tectonic Plates) -> Chapter 4: The Extreme Machinery (Custom Mega-Boring Drills & Massive Hydraulic Systems) -> Chapter 5: The Near-Catastrophe Crisis (The Structural Crack, Flash Flood Or Financial Run) -> Chapter 6: The Modern Arteries (How This Single Megastructure Anchors The Global Economy)",
            "chapter_format": "[Chapter: <Title>]"
        },
        "image_automation": {
            "visual_style": "hyper-realistic 3D isometric architectural cutaways, structural cross-sections showing foundation piles and subterranean pipes, wireframe blueprint transitions into photorealistic engineering renders, satellite geospatial zoomouts, technical metric callouts, warm golden-hour architectural lighting, pristine cinematic clarity, grand engineering scale",
            "aspect_ratio": "16:9",
            "negative_prompt": "cartoon, 2d doodle, low polygon, plastic textures, blurry water, bad perspective, inaccurate physics, flat lighting, text artifacts, watermark",
            "model": "Imagen 3",
            "generation_mode": "image",
            "character_consistency": "Hardhat-wearing structural engineers and geotechnical specialists surveying colossal machinery, inspecting concrete foundation vaults, standing on dizzying observation decks.",
            "environment_consistency": "Massive concrete dam spillways churning white water, deep sub-sea tunnel boring vaults, gleaming desert solar-desalination megastructures, bustling deep-water shipping straits at dusk.",
            "cinematic_style": "Sweeping IMAX architectural cinematography, smooth 3D isometric cutaways floating in space, technical blueprint overlay dissolves, monumental low-angle scale."
        },
        "video_forge": {
            "allowed_transitions": ["smoothleft", "smoothright", "dissolve", "fade", "horzopen"],
            "video_styling": "Hyper-detailed mega-engineering 3D cutaway and isometric technical motion graphics",
            "sub_mode": "karaoke",
            "sub_position": "bottom_center",
            "subtitle_font": "Bahnschrift",
            "subtitle_font_size": 54,
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_spacing": 1.2,
            "subtitle_uppercase": False,
            "subtitle_primary_color": "&H00FFFFFF",
            "subtitle_karaoke_color": "&H00FFD400",
            "subtitle_karaoke_outline": "&H000A1A24",
            "subtitle_outline_color": "&H000A141E",
            "subtitle_back_color": "&H90081018",
            "subtitle_outline_width": 2.8,
            "subtitle_shadow": 1.6,
            "subtitle_border_style": 1,
            "subtitle_alignment": 2,
            "subtitle_animation": "glow",
            "subtitle_margin_v": 65,
            "subtitle_max_chars": 36
        },
        "niche_topics": [
            "The Strait Of Hormuz Trap: Why The Worlds Most Critical Oil Chokepoint Has No Exit",
            "How A Country With Zero Rivers Drinks Water: Saudi Arabias Mega-Desalination Grid",
            "Why Isnt Dubais Palm Jumeirah Sinking? The Extreme Ocean Engineering Behind The Island",
            "How The 3,000-Year-Old Suez Canal Was Carved Through 120 Miles Of Shifting Desert",
            "How Did Venice Build A Stone Empire On Water With 10 Million Wooden Tree Trunks?",
            "The Impossible Panama Canal Expansion: How Engineers Lifted 1,200-Foot Ships Over A Mountain",
            "How The Three Gorges Dam Slowed Earths Rotation: The Scale Of The Worlds Biggest Dam",
            "The Millau Viaduct: How France Built A Highway That Floats Above The Clouds",
            "How The Channel Tunnel Connected Britain And France 150 Feet Beneath The Sea",
            "The Megastructure Sinking In San Francisco: The 58-Story Millennium Tower Engineering Crisis",
            "How Singapore Turns Sewage Into Ultra-Pure Drinking Water With Zero Natural Lakes",
            "The Gotthard Base Tunnel: Drilling 35 Miles Through Solid Alpine Granite",
            "Why The Leaning Tower Of Pisa Stopped Leaning: The Soil Extraction Miracle",
            "How The Burj Khalifa Survives 100 MPH Desert Winds At Half A Mile High",
            "The MOSE Barrier: The $6 Billion Floating Steel Dam Fighting Venices Rising Tides",
            "How The Netherlands Reclaimed 27% Of Its Entire Country From The North Sea",
            "The Itaipu Dam: The Megastructure That Powers Two Entire Nations",
            "How The Hoover Dam Cured Concrete For 50 Years In 115-Degree Nevada Desert",
            "The Danyang-Kunshan Grand Bridge: Building A 102-Mile Viaduct Over Water And Quicksand",
            "How Japan Built Kansai Airport On A Sinking Man-Made Island In Osaka Bay"
        ],
        "thumbnail_styles": [
            {
                "id": "strait_chokepoint_blockade",
                "name": "The Chokepoint Stranglehold",
                "description": "Ultra-wide photorealistic satellite perspective of a narrow maritime strait between dramatic sheer mountain cliffs, where a gigantic ultra-large container ship is angled dangerously across the shipping channel, surrounding waters filled with glowing golden maritime shipping lanes abruptly choked to a halt, sunset lighting, no text."
            },
            {
                "id": "desert_water_aqueduct_cutaway",
                "name": "The Subterranean Water Highway",
                "description": "Breathtaking 3D architectural cross-section cutaway showing a scorched, endless red desert surface, sliced open to reveal massive 5-meter pressurized steel water pipelines and glowing blue underground aquifer reservoirs roaring beneath the dunes, extreme scale, no text."
            },
            {
                "id": "floating_foundation_monolith",
                "name": "The Island That Defies Gravity",
                "description": "Isometric cutaway render of a luxury artificial palm island in turquoise ocean waters, revealing thousands of massive vibrating stone compaction piles driven into the seabed to hold back liquefaction, dramatic engineering precision, no text."
            }
        ],
        "offline_voice": "Michael·  American Male",
        "elevenlabs_voice": "Jonathan - Professional, Calm, Credible, Clear  ·  ElevenLabs (Male)",
        "voices": {
            "offline": "Michael·  American Male",
            "elevenlabs": "Jonathan - Professional, Calm, Credible, Clear  ·  ElevenLabs (Male)"
        }
    },
    "nostalgia_rock": {
        "preset_name": "nostalgia_rock",
        "display_name": "Nostalgia Rock",
        "description": "Emotionally charged classic rock history, 1950s-1980s music tragedies, forgotten one-hit wonders, heartbreaking song lore, and vanished musical legends.",
        "voice_name": "Fenrir ·  American Male",
        "video_language": "English",
        "content_automation": {
            "title_structure": "The [Saddest/Most Tragic] [Song/Rock Band] Of The [1970s/1980s] That [Broke Millions Of Hearts/Vanished Without A Trace]",
            "hook_style": "Deep emotional nostalgia and high-stakes musical tragedy. A legendary melody that concealed a devastating personal heartbreak.",
            "target_words": 2100,
            "target_duration_minutes": 11,
            "tone": "Soulful, nostalgic, haunting, cinematic rock-and-roll retrospective with deep emotional empathy and melancholic reverence.",
            "pacing": "Warm, rhythmic, soulful storytelling, 155-170 wpm, pausing for musical resonance and poignant lyrical milestones.",
            "scene_density": "1 visual scene every 3-4 sentences",
            "narrative_structure": "Chapter-based musical retrospective (6 chapters): Chapter 1: The Melody That Haunted A Generation (The Heartbreaking Hook) -> Chapter 2: The Hungry Basement Years (The Rise, The Chemistry & The Golden Album) -> Chapter 3: The Secret Agony (Addiction, Betrayal & The Cracking Facade) -> Chapter 4: The 3 A.M. Recording Session (The Improvised Masterpiece Born In Grief) -> Chapter 5: The Sudden Shattering (The Final Concert, The Crash Or The Vanishing) -> Chapter 6: The Ghost In The Vinyl (Why This Song Still Brings Grown Men To Tears Decades Later)",
            "chapter_format": "[Chapter: <Title>]"
        },
        "image_automation": {
            "visual_style": "vintage rock-and-roll 35mm photography aesthetic, authentic Kodachrome and Ektachrome film grain, warm analog color grading, moody concert stage spotlights through haze and smoke, worn vinyl record grooves, vintage Fender amplifiers and microphone close-ups, 1970s psychedelic gatefold album typography, intimate archival backstage photography, deep soulful amber and sepia tones",
            "aspect_ratio": "16:9",
            "negative_prompt": "modern digital clean, 3d CGI, plastic sheen, anime, flat modern vector, mobile phones, modern laptops, oversaturated neon, text artifacts, watermark",
            "model": "Imagen 3",
            "generation_mode": "image",
            "character_consistency": "Charismatic, weathered 1970s and 1980s rock musicians with authentic shaggy hair, leather jackets, vintage aviators, singing into vintage microphones with raw visceral emotion.",
            "environment_consistency": "Smoky analog sound studios with reel-to-reel tape decks, packed 1970s stadium stages with wall-of-sound Marshall stacks, late-night rain-slicked roadside diners with glowing neon signs.",
            "cinematic_style": "Candid 35mm documentary rock cinematography, evocative slow push-ins on vintage record players and guitar fretboards, warm analog halation and stage light flares."
        },
        "video_forge": {
            "allowed_transitions": ["dissolve", "fade", "smoothleft", "radial", "pixelize"],
            "video_styling": "Vintage 35mm rock-and-roll analog film retrospective with warm stage lighting",
            "sub_mode": "karaoke",
            "sub_position": "bottom_center",
            "subtitle_font": "Impact",
            "subtitle_font_size": 62,
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_spacing": 0.6,
            "subtitle_uppercase": True,
            "subtitle_primary_color": "&H00E6F5FF",
            "subtitle_karaoke_color": "&H000077FF",
            "subtitle_karaoke_outline": "&H000A0505",
            "subtitle_outline_color": "&H00100808",
            "subtitle_back_color": "&HB00A0505",
            "subtitle_outline_width": 3.6,
            "subtitle_shadow": 2.5,
            "subtitle_border_style": 1,
            "subtitle_alignment": 2,
            "subtitle_animation": "bounce",
            "subtitle_margin_v": 70,
            "subtitle_max_chars": 32
        },
        "niche_topics": [
            "The 15 Saddest Songs Of The 1970s No One Can Listen To Without Crying",
            "The 10 Saddest Songs Of The 1980s That Broke Millions Of Hearts",
            "The Forgotten 80s Band That Sold 10 Million Records Then Vanished Without A Trace",
            "10 One-Hit Wonders Everyone Remembers From 1975: The Tragic Stories Behind The Hits",
            "The Heartbreaking Final Recording Session Of Freddie Mercury And Queen",
            "Why Creedence Clearwater Revival Broke Up At Their Absolute Peak In 1972",
            "The 1977 Plane Crash That Shattered Lynyrd Skynyrd: What Really Happened",
            "The Tragic Disappearance Of Richey Edwards: Rocks Most Chilling Unsolved Mystery",
            "How Fleetwood Mac Recorded Rumours While Secretly Hating Each Others Guts",
            "The 15 Catchiest Classic Rock Riffs Of The 1960s You Never Got Out Of Your Head",
            "The Dark True Story Behind Eric Claptons Tears In Heaven",
            "10 Forgotten Hard Rock Gems Of The 1970s That Still Hit Harder Than Modern Rock",
            "The Tragic 27 Club: The Uncanny Curse That Took Hendrix, Joplin, And Morrison",
            "How Led Zeppelin Stole Their Greatest Riffs (And Still Conquered Stadium Rock)",
            "The Day The Music Died: The 1959 Plane Crash That Changed Rock And Roll Forever",
            "Why The Eagles Ended Up In A $25 Million Fistfight In Long Beach",
            "The 10 Most Shocking Backstage Scandals In 1970s Rock History",
            "The Forgotten Soul Singer Whose Hit Song Saved Motown From Bankruptcy",
            "How Pink Floyd Created The Dark Side Of The Moon In Absolute Creative Agony",
            "The Last Days Of John Bonham And The Sudden End Of Led Zeppelin"
        ],
        "thumbnail_styles": [
            {
                "id": "empty_spotlight_microphone",
                "name": "The Ghost At The Microphone",
                "description": "An empty vintage chrome Shure microphone standing on a dark, smoke-filled wooden concert stage under a solitary piercing warm amber spotlight, guitar feedback haze in the air, a battered 1970s sunburst Stratocaster leaning against an amplifier in the shadows, deep melancholic nostalgia, no text."
            },
            {
                "id": "shattered_vinyl_master",
                "name": "The Broken Golden Record",
                "description": "Extreme close-up of a classic 1970s black vinyl record cracked down the center, with golden light bursting through the fracture, resting on a worn leather tour road case surrounded by vintage cassette tapes and scribbled lyrics, warm Kodachrome film grain, no text."
            },
            {
                "id": "backstage_solitary_genius",
                "name": "The Backstage Silhouette",
                "description": "Gritty 35mm candid perspective from a dark backstage stadium tunnel; a solitary legendary rock frontman holding his head in his hands right before stepping into the blinding roar of a 50,000-person stadium light wall, intense emotional contrast, no text."
            }
        ],
        "offline_voice": "Fenrir ·  American Male",
        "elevenlabs_voice": "Steve  ·  ElevenLabs (Male)",
        "voices": {
            "offline": "Fenrir ·  American Male",
            "elevenlabs": "Steve  ·  ElevenLabs (Male)"
        }
    },
    "psych_toons": {
        "preset_name": "psych_toons",
        "display_name": "Psych Toons",
        "description": "Clean psychological explainer animations, dark triad analysis, social intelligence frameworks, cognitive biases, and mental resilience models.",
        "voice_name": "Michael·  American Male",
        "video_language": "English",
        "content_automation": {
            "title_structure": "Psychology of [Topic/Social Trait]: How To [Outsmart Anyone/Never Run Out Of Things To Say/Read Anyone Instantly]",
            "hook_style": "Immediate psychological validation of a universal social pain point or an unfair cognitive advantage.",
            "target_words": 1900,
            "target_duration_minutes": 10,
            "tone": "Sharp, insightful, empowering, conversational pop-psychology, intellectually crisp with zero academic fluff.",
            "pacing": "Punchy, engaging, upbeat momentum, 165-180 wpm, clear mental shifts punctuated by memorable psychological laws.",
            "scene_density": "1 visual scene every 2-3 sentences",
            "narrative_structure": "Chapter-based cognitive framework (5-6 chapters): Chapter 1: The Social Blind Spot (The Painful Reality & The 1% Counter-Intuitive Truth) -> Chapter 2: The Cognitive Architecture (Why Human Psychology Is Hardwired To React This Way) -> Chapter 3: The Dark Triad & Machiavellian Trap (How Toxic Manipulators Weaponize This Dynamic) -> Chapter 4: The 4-Step Mental Framework (The Exact Internal Shift To Reclaim Power) -> Chapter 5: Real-World Social Scenarios (Word-For-Word Examples In High-Stakes Situations) -> Chapter 6: The Unshakeable Mindset (Integrating The Shadow & Effortless Composure)",
            "chapter_format": "[Chapter: <Title>]"
        },
        "image_automation": {
            "visual_style": "minimalist 2D psychological character cartoon animation, smooth rounded vector shapes, clean modern pastel dark slate canvas (#1A1E29), vivid electric violet (#A855F7) and electric cyan (#06B6D4) glowing accent elements, expressive cartoon avatars, visual psychological metaphors (glowing brain neurons, shadow silhouettes, chess pieces, puppet strings, cracked masks), high graphic novel linework clarity, crisp flat design",
            "aspect_ratio": "16:9",
            "negative_prompt": "photorealism, 3d hyper-detailed CGI, gritty textures, muddy dark gradients, chaotic busy backgrounds, warped hands, ugly faces, text artifacts, watermark",
            "model": "Imagen 3",
            "generation_mode": "image",
            "character_consistency": "Clean, expressive minimalist 2D stylized cartoon characters with solid dark hair, distinct posture, and highly readable emotional expressions (calm stoicism, smirking confidence, curious calculation).",
            "environment_consistency": "Abstract conceptual psychological stages: floating geometric platforms, clean modern minimalist rooms, stark spotlight cones on dark slate void (#1A1E29).",
            "cinematic_style": "Dynamic 2D animation storyboarding, crisp figure-ground separation, punchy framing shifts from wide mental diagrams to expressive character reaction close-ups."
        },
        "video_forge": {
            "allowed_transitions": ["smoothleft", "smoothright", "circleopen", "fade", "dissolve"],
            "video_styling": "Clean 2D animated psychological explainer with kinetic character motion",
            "sub_mode": "karaoke",
            "sub_position": "bottom_center",
            "subtitle_font": "Trebuchet MS",
            "subtitle_font_size": 56,
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_spacing": 0.5,
            "subtitle_uppercase": False,
            "subtitle_primary_color": "&H00FFFFFF",
            "subtitle_karaoke_color": "&H00F755A8",
            "subtitle_karaoke_outline": "&H0024101A",
            "subtitle_outline_color": "&H00201624",
            "subtitle_back_color": "&H80181020",
            "subtitle_outline_width": 3.0,
            "subtitle_shadow": 2.0,
            "subtitle_border_style": 1,
            "subtitle_alignment": 2,
            "subtitle_animation": "bounce",
            "subtitle_margin_v": 65,
            "subtitle_max_chars": 34
        },
        "niche_topics": [
            "Psychology Of Social Intelligence: How To Read Anyone Instantly In 60 Seconds",
            "How To Deal With People Who Disrespect You (Without Ever Losing Your Cool)",
            "Psychology Of Verbal Intelligence: How To Articulate Complex Thoughts With Razor Precision",
            "Psychology Of Machiavellianism: Why Trying To Please Everyone Guarantees Failure",
            "The Psychology Of Not Giving A F*ck: How To Detach From Outcome Anxiety",
            "Psychology Of The Shadow: Why Integrating Your Dark Side Is The Secret To Inner Strength",
            "The 6 Dangerous Personality Types Psychology Warns You Must Avoid At All Costs",
            "Psychology Of Composure: How To Stay So Calm In Chaos It Intimidates Others",
            "Why Some People Are Meant To Walk Alone: The Psychology Of The Solitary Mindset",
            "Psychology Of Confidence: How To Stop Seeking External Validation Forever",
            "The Danger Of Seeing What Others Do Not: The Cognitive Burden Of High Perception",
            "10 Psychological Habits That Build An Unshakeable Bulletproof Mindset",
            "Psychology Of Discipline: How To Trick Your Dopamine System Into Loving Hard Work",
            "Psychology Of Charisma: The Micro-Behaviors That Make Anyone Magnetic Instantly",
            "Psychology Of Power: How To Establish Dominance Without Saying A Single Word",
            "Psychology Of People Who Go Completely Quiet When They Are Deeply Hurt",
            "The Cognitive Trap Of Overthinking: How To Break The Rumination Loop In 5 Minutes",
            "Psychology Of Problem Solving: 10 Mental Models To Navigate Crisis On Easy Mode",
            "Why High Intelligence Often Leads To Deep Social Isolation (And The Antidote)",
            "Psychology Of Resilience: Building A Mind So Unyielding That Failure Becomes Fuel"
        ],
        "thumbnail_styles": [
            {
                "id": "the_shadow_puppet_mind",
                "name": "The Shadow Master",
                "description": "Minimalist 2D vector scene on a deep slate background (#1A1E29); a clean, calm cartoon figure stands composed in the light, while behind them their elongated dark silhouette looms massive on the wall, holding glowing puppeteer strings that control two opposing arguing characters, bold purple and cyan glow accents, no text."
            },
            {
                "id": "the_cracked_social_mask",
                "name": "The Mask Of Composure",
                "description": "Striking side-profile close-up of a stylish cartoon face split down the middle: one half is a smooth smiling white porcelain mask, while the other half reveals an intricate, glowing neon clockwork brain with intense electric violet sparks and calculated focus, high chromatic tension, no text."
            },
            {
                "id": "the_unseen_chess_move",
                "name": "The Invisible Pawn Gambit",
                "description": "Overhead minimalist perspective of a giant glossy dark chessboard; a small, confident cartoon character casually pushes a single glowing neon blue pawn forward, while across the board a towering, arrogant crowned king figure begins to shatter into geometric dust, no text."
            }
        ],
        "offline_voice": "Michael·  American Male",
        "elevenlabs_voice": "Jeremy - Young, Confident, American Male  ·  ElevenLabs (Male)",
        "voices": {
            "offline": "Michael·  American Male",
            "elevenlabs": "Jeremy - Young, Confident, American Male  ·  ElevenLabs (Male)"
        }
    }
}

for k, v in NEW_PRESETS.items():
    registry[k] = v
    print(f"Added/Updated preset in registry: {k}")

registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Successfully updated master registry with {len(NEW_PRESETS)} presets! Total presets now: {len(registry)}")
