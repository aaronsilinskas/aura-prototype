# Pack versions are MAJOR.MINOR; a scene names the minimum it needs

Every **Effect pack** and **Rule pack** states a `MAJOR.MINOR` version in its **Pack manifest**. `Version.parse` rejects anything else: one component, three, or a non-digit part. A scene names each pack it uses with the version it needs, and the installed pack satisfies it when the majors are equal and the installed minor is at least the required one. The **PackCatalog** scan checks every scene's packs this way before boot continues, and `IncompatiblePackError` names the scene, the pack and both versions (#1098).

The rule has been the pack contract since `PackRegistry` was first built (#87). ADR-0003, ADR-0004 and ADR-0006 rely on it when they say which change to a pack's Settings, `requires` or verbs is a minor bump and which is a major. Each records what bumps the version, not this compatibility rule. Why it has two components and a minimum minor is not recorded. The likely reasons, to be confirmed: a card holds one installed copy of each pack, so a scene can only ask for the least it needs; a minor bump adds without breaking, so any newer minor serves an older scene; and a fix that leaves the interface alone needs no version change, so a third, patch component would carry nothing the check reads.

## Consequences

- A scene that needs a newer minor fails the scan on a card with an older one, and so does a scene written for a different major, older or newer.
- A pack's author must bump the major for any change that could break a scene written against the old version, because nothing else stops that scene from loading.
- A version is a string in JSON: a JSON number such as `1.2` is malformed.
