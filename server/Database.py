from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from uuid import uuid4

class Database:
    def __init__(self, mongo_client: AsyncIOMotorClient, dev: bool):
        # Initialize the class with a MongoClient object 
        self.client = mongo_client
        # Set the database to the dev database if dev is True, otherwise set it to the prod database (in order to avoid overwriting the prod database because I'm a dumbass)
        if dev:
            self.db = self.client["dev"]
            from BaseballData import BaseballData
            self.BaseballData = BaseballData
        else:
            self.db = self.client["prod"]
            from server.BaseballData import BaseballData
            self.BaseballData = BaseballData

        self.collection = self.db["matchup-statistics"]
        self.share_collection = self.db["shared-grids"]
    
    def __normalize_team_names(self, teams: tuple[str, str]) -> str:
        string = teams[0].lower().replace(" ", "") + teams[1].lower().replace(" ", "")
        return "".join(sorted(string))
    
    def __normalize_player_name(self, player: str, id: str) -> str:
        return player.lower().replace(" ", "").replace(".", "") + id
    
    def __get_id(self, player: str):
        return player[-6:]

    def __matchup(self, teams: tuple[str, str], player: str) -> str:
        template = {
            "team_combination": self.__normalize_team_names(teams),
            "total_picks": 1,
            "players": {
                player: {
                    "pick_frequency": 1
                }
            }
        }
        return template
    
    # Query the MongoDB database to find the player if they exist in the team combination
    async def __find_player(self, teams: tuple[str, str], player: str):
        matchup = self.__normalize_team_names(teams)
        return await self.collection.find_one({"team_combination": matchup, f"players.{player}": {"$exists": True}})

    async def __add_matchup(self, team1: str, team2: str, player: str):
        await self.collection.insert_one(self.__matchup((team1, team2), player))

    async def update_matchup(self, teams: tuple[str, str], player: str, id: str):
        original_player_name = player  # Preserve original player name
        player = self.__normalize_player_name(player, id)
        matchup = self.__normalize_team_names(teams)
        if await self.collection.find_one({"team_combination": matchup}):
            if await self.__find_player(teams, player):
                return await self.collection.update_one(
                    {"team_combination": matchup}, 
                    {
                        "$inc": {"total_picks": 1, f"players.{player}.pick_frequency": 1}, 
                        "$set": {f"players.{player}.un_normalized_name": original_player_name}
                    }
                )
            return await self.collection.update_one(
                {"team_combination": matchup}, 
                {
                    "$inc": {"total_picks": 1}, 
                    "$set": {f"players.{player}": {"un_normalized_name": original_player_name, "pick_frequency": 1}}
                }
            )
        return await self.__add_matchup(teams[0], teams[1], player)
    
    async def calculate_rarity_score(self, teams: tuple[str, str], player: str, id: str):
        matchup = self.__normalize_team_names(teams)
        player = self.__normalize_player_name(player, id)
        data = await self.collection.find_one({"team_combination": matchup})
        if data:
            if await self.collection.find_one({"team_combination": matchup, f"players.{player}": {"$exists": True}}):
                total_picks = data["total_picks"]
                pick_frequency = data["players"][player]["pick_frequency"]
                score: float = round((pick_frequency / total_picks) * 100, 2)
                if score > 1:
                    return int(score)
                return score
        return 100
    
    async def set_shared_grid(self, grid: list[list[str]]) -> str:
        id = str(uuid4())
        await self.share_collection.insert_one({"id": id, "grid": grid})
        return id
    
    async def get_shared_grid(self, id: str) -> list[list[str]]:
        data = await self.share_collection.find_one({"id": id})
        if data:
            return data["grid"]
        return []
    

    def key_function(self, x, data):
        try:
            return data["players"][x]["pick_frequency"]
        except KeyError:
            return -1

    async def get_top_player(self, teams: tuple[str, str]):
        matchup = self.__normalize_team_names(teams)
        data = await self.collection.find_one({"team_combination": matchup})
        if data:
                top_player = max(data["players"], key=lambda x: self.key_function(x, data))
                if "un_normalized_name" in data["players"][top_player]:
                    top_player_name = data["players"][top_player]["un_normalized_name"]
                    top_player_id = self.__get_id(top_player)
                    top_player_rarity = await self.calculate_rarity_score(teams, top_player_name, top_player_id)
                    top_player_picture = self.BaseballData.get_player_picture(id=top_player_id)
                    return {"name": top_player_name, "picture": top_player_picture, "rarity_score": top_player_rarity}
                return 0
        return 0
    
    async def add_player_name(self, matchup: str, name: str):
        await self.collection.update_one({"team_combination": matchup}, {"$set": {f"players.{self.__normalize_player_name(name)}.un_normalized_name": name}})

    @staticmethod
    def unnormalize_team_names(normalized_string: str) -> tuple[str, str]:
        mlb_teams = [
            "Baltimore Orioles",
            "Boston Red Sox",
            "New York Yankees",
            "Tampa Bay Rays",
            "Toronto Blue Jays",
            "Chicago White Sox",
            "Cleveland Guardians",
            "Detroit Tigers",
            "Kansas City Royals",
            "Minnesota Twins",
            "Houston Astros",
            "Los Angeles Angels",
            "Oakland Athletics",
            "Seattle Mariners",
            "Texas Rangers",
            "Atlanta Braves",
            "Miami Marlins",
            "New York Mets",
            "Philadelphia Phillies",
            "Washington Nationals",
            "Chicago Cubs",
            "Cincinnati Reds",
            "Milwaukee Brewers",
            "Pittsburgh Pirates",
            "St. Louis Cardinals",
            "Arizona Diamondbacks",
            "Colorado Rockies",
            "Los Angeles Dodgers",
            "San Diego Padres",
            "San Francisco Giants",
        ]

        for i, team1 in enumerate(mlb_teams):
            for team2 in mlb_teams[i + 1:]:
                # Lowercase and combine the names
                combined = team1.lower().replace(" ", "") + team2.lower().replace(" ", "")
                normalized = "".join(sorted(combined))
                # Check if the sorted string matches
                if normalized == normalized_string:
                    return team1, team2
        return None
