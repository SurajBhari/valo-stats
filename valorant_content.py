"""Riot content lookup tables: agent UUIDs, map paths, weapon UUIDs → names."""

AGENT_MAPPING = {
    "1dbf2edd-4729-0984-3115-daa5eed44993": "Clove",
    "dade69b4-4f5a-8528-247b-219e5a1facd6": "Fade",
    "add6443a-41bd-e414-f6ad-e58d267f4e95": "Jett",
    "6f2a04ca-43e0-be17-7f36-b3908627744d": "Skye",
    "eb93336a-449b-9c1b-0a54-a891f7921d69": "Phoenix",
    "22697a3d-45bf-8dd7-4fec-84a9e28c69d7": "Chamber",
    "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc": "Reyna",
    "569fdd95-4d10-43ab-ca70-79becc718b46": "Sage",
    "95b78ed7-4637-86d9-7e41-71ba8c293152": "Harbor",
    "e370fa57-4757-3604-3648-499e1f642d3f": "Gekko",
    "41fb69c1-4189-7b37-f117-bcaf1e96f1bf": "Astra",
    "7c8a4701-4de6-9355-b254-e09bc2a34b72": "Miks",
    "5f8d3a7f-467b-97f3-062c-13acf203c006": "Breach",
    "92eeef5d-43b5-1d4a-8d03-b3927a09034b": "Veto",
    "f94c3b30-42be-e959-889c-5aa313dba261": "Raze",
    "117ed9e3-49f3-6512-3ccf-0cada7e3823b": "Cypher",
    "320b2a48-4d9b-a075-30f1-1f93a9b638fa": "Sova",
    "b444168c-4e35-8076-db47-ef9bf368f384": "Tejo",
    "8e253930-4c05-31dd-1b6c-968525494517": "Omen",
    "df1cb487-4902-002e-5c17-d28e83e78588": "Waylay",
    "7f94d92c-4234-0a36-9646-3a87eb8b5c89": "Yoru",
    "bb2a4828-46eb-8cd1-e765-15848195d751": "Neon",
    "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235": "Deadlock",
    "601dbbe7-43ce-be57-2a40-4abd24953621": "KAY/O",
    "1e58de9c-4950-5125-93e9-a0aee9f98746": "Killjoy",
    "efba5359-4016-a1e5-7626-b1ae76895940": "Vyse",
    "707eab51-4836-f488-046a-cda6bf494859": "Viper",
    "9f0d8ba9-4140-b941-57d3-a7ad57c6b417": "Brimstone",
    "0e38b510-41a8-5780-5e8f-568b2a4f2d6c": "Iso",
}

MAP_MAPPING = {
    "/Game/Maps/Ascent/Ascent": "Ascent",
    "/Game/Maps/Bonsai/Bonsai": "Split",
    "/Game/Maps/Canyon/Canyon": "Fracture",
    "/Game/Maps/Duality/Duality": "Bind",
    "/Game/Maps/Foxtrot/Foxtrot": "Breeze",
    "/Game/Maps/Jam/Jam": "Lotus",
    "/Game/Maps/Jujutsu/Jujutsu": "Abyss",
    "/Game/Maps/Pitt/Pitt": "Pearl",
    "/Game/Maps/Port/Port": "Icebox",
    "/Game/Maps/Triad/Triad": "Haven",
    "/Game/Maps/Pangea/Pangea": "Sunset",
    "/Game/Maps/Rook/Rook": "Corrode",
}

WEAPON_MAPPING = {
    "63e6c2b6-4a8e-869c-3d4c-e38355226584": "Odin",
    "55d8a0f4-4274-ca67-fe2c-06ab45efdf58": "Ares",
    "9c82e19d-4575-0200-1a81-3eacf00cf872": "Vandal",
    "ae3de142-4d85-2547-dd26-4e90bed35cf7": "Bulldog",
    "ee8e8d15-496b-07ac-e5f6-8fae5d4c7b1a": "Phantom",
    "ec845bf4-4f79-ddda-a3da-0db3774b2794": "Judge",
    "910be174-449b-c412-ab22-d0873436b21b": "Bucky",
    "44d4e95c-4157-0037-81b2-17841bf2e8e3": "Frenzy",
    "29a0cfab-485b-f5d5-779a-b59f85e204a8": "Classic",
    "410b2e0b-4ceb-1321-1727-20858f7f3477": "Bandit",
    "1baa85b4-4c70-1284-64bb-6481dfc3bb4e": "Ghost",
    "e336c6b8-418d-9340-d77f-7a9e4cfe0702": "Sheriff",
    "42da8ccc-40d5-affc-beec-15aa47b42eda": "Shorty",
    "a03b24d3-4319-996d-0f8c-94bbfba1dfc7": "Operator",
    "4ade7faa-4cf1-8376-95ef-39884480959b": "Guardian",
    "5f0aaf7a-4289-3998-d5ff-eb9a5cf7ef5c": "Outlaw",
    "c4883e50-4494-202c-3ec3-6b8a9284f00b": "Marshal",
    "462080d1-4035-2937-7c09-27aa2a5c27a7": "Spectre",
    "f7e1b454-4ad4-1063-ec0a-159e56b58941": "Stinger",
    "2f59173c-4bed-b6c3-2191-dea9b58be9c7": "Melee",
}


def agent_name(uuid: str) -> str:
    """Return the agent display name for a UUID, or 'Unknown' if not found."""
    return AGENT_MAPPING.get(uuid, "Unknown")


def map_name(path: str) -> str:
    """Return the map display name for a Riot map path.

    Falls back to the last non-empty segment of the path for unknown maps,
    or 'Unknown' if the path is empty/None.
    """
    if not path:
        return "Unknown"
    if path in MAP_MAPPING:
        return MAP_MAPPING[path]
    # Fallback: last non-empty segment
    segments = [s for s in path.split("/") if s]
    return segments[-1] if segments else "Unknown"


def weapon_name(uuid: str) -> str:
    """Return the weapon display name for a UUID, or 'Unknown' if not found."""
    return WEAPON_MAPPING.get(uuid, "Unknown")
