# MIDI Source Strategy

OpenOrchestrion needs two different concepts: **free to download** and **safe to redistribute**. They are not the same thing.

## Strong open-library candidates

### Mutopia Project

Useful for classical, piano, ragtime, chamber and some orchestral material. Individual works identify their public-domain or Creative Commons status. This is a strong candidate for a verified/open starter library.

### Wikimedia Commons

Accepts public-domain or freely licensed media. Individual file terms still need to be retained, including attribution/share-alike requirements where applicable.

### MAESTRO

A large expressive piano-performance dataset captured from Yamaha Disklavier instruments. Particularly attractive because the MIDI includes real performance timing, velocity and pedals. The MIDI-only dataset is very small relative to its roughly 200 hours of music. Dataset licensing must be respected; it should not simply be copied into the repo without reviewing redistribution terms.

## Free-download sources with rights caveats

Sites such as BitMidi and VGMusic can contain huge catalogs, including pop, film, game and other modern music. A file being downloadable without charge does **not** make the composition or arrangement public domain.

OpenOrchestrion may support these files as **Personal Library** imports where appropriate, but the public repository should not redistribute them without clear rights.

## Two-piano material

The project should actively curate or index legally usable:

- true two-piano works;
- piano four-hands material whose parts can be separated;
- public-domain two-piano arrangements;
- purpose-built OpenOrchestrion dueling-piano arrangements.

A useful proof-of-concept target is Mozart's Sonata for Two Pianos in D major, K.448, using a MIDI source whose redistribution terms are compatible with the chosen use.

## General MIDI arrangements

GM/GM1 files are especially valuable because they can carry standardized instrument assignments and percussion conventions that a compatible hardware engine can interpret directly.

The importer should record whether a file appears GM-compatible and which programs/channels it requests.

## Library policy

Every indexed or bundled file should track:

- source URL/reference;
- original creator/arranger when known;
- composition rights status;
- file/arrangement license;
- attribution text if required;
- redistribution status (`verified-open`, `personal`, `unknown`);
- date imported/verified.

The public project should favor a smaller, high-quality, legally clean starter catalog over an enormous mystery archive.
