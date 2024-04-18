import re
import webbrowser
from unrealsdk import *

from Mods.ModMenu import (
    EnabledSaveType,
    Game,
    Hook,
    Keybind,
    KeybindManager,
    Mods,
    ModTypes,
    RegisterMod,
    SDKMod,
    Options,
) 

try:
    from Mods.PythonPartNotifier import get_single_part_name

    from Mods.UserFeedback import (
        OptionBox,
        OptionBoxButton,
        TrainingBox
    )
except ImportError:
    webbrowser.open("https://bl-sdk.github.io/requirements/?mod=Spare%20Parts&UserFeedback&Python%20Part%20Notifier")
    raise


class SpareParts(SDKMod):
    Name: str = "Spare Parts"
    Author: str = "LaryIsland"
    Description: str = "<font size='26' color='#de5b00'>Spare Parts</font>\n\n" \
        "Allows you to salvage parts from items and attach them to other items.\n\n" \
        "Just select an item from your backpack, hover over another item " \
        "and press the 'salvage' hotkey. Default is [C]\n\n" \
        "Note: the item you salvage parts from will be destroyed in the process."
    Version: str = "1.2"

    SupportedGames: Game = Game.BL2
    Types: ModTypes = ModTypes.Utility
    
    SaveEnabledState: EnabledSaveType = EnabledSaveType.LoadWithSettings

    def __init__(self) -> None:
        super().__init__()
        self._salvageHotkey: Keybind = Keybind(
            "Salvage Item Parts",
            "C",
            True,
        )
        self.Keybinds = [self._salvageHotkey]
        self.UserInterface = SparePartsUI(self)
        self.Globals = FindObject("GlobalsDefinition", "GD_Globals.General.Globals")
        
        self.RarityLock = Options.Boolean(
            Caption="Rarity Lock",
            Description="Only allow salvaging parts from items of the same or higher rarity.",
            StartingValue=True,
            Choices=["Off", "On"]
        )
        self.StrictUniques = Options.Boolean(
            Caption="Strict Uniques",
            Description="Unique items can only salvage parts from the same unique items.\t" \
                "E.g. An Unkempt Harold can only salvage parts from another Unkempt Harold.",
            StartingValue=True,
            Choices=["Off", "On"]
        )
        self.SanityCheckSafeguard = Options.Spinner(
            Caption="Sanity Check Safeguard",
            Description="Safe: Every part combination will pass the sanity check.\n" \
                "Expert: Extra potentially unsafe Relic and COM parts.\n" \
                "Insane: Removes all checks and safeguards.",
            StartingValue="Safe",
            Choices=["Safe", "Expert", "Insane"]
        )
        
        self.Options = [
            self.RarityLock,
            self.StrictUniques,
            self.SanityCheckSafeguard,
        ]

    SettingsInputs = SDKMod.SettingsInputs.copy()
    SettingsInputs["G"] = "GitHub"
    
    def SettingsInputPressed(self, action: str) -> None:
        if action == "GitHub":
            webbrowser.open("https://github.com/LaryIsland/bl-sdk-mods/tree/main/SpareParts")
        else:
            super().SettingsInputPressed(action)


    @Hook("WillowGame.ItemInspectionGFxMovie.OnClose")
    def _inspectOnClose(
        self,
        caller: UObject,
        function: UFunction,
        params: FStruct,
    ) -> bool:
        if self.UserInterface.inspecting:
            self.UserInterface.inspecting = False
            self.UserInterface.showGuidedReplacements()
        return True
    
    
    @Hook("WillowGame.StatusMenuInventoryPanelGFxObject.SetTooltipText")
    def _setTooltipText(
        self,
        caller: UObject,
        function: UFunction,
        params: FStruct,
    ) -> bool:

        if caller.bInEquippedView is True:
            return True
        
        if caller.bIsDoingEquip is False:
            return True
        
        if caller.EquippingThing == caller.GetSelectedThing():
            return True

        result: str = ""
        result = f"{params.TooltipsText}\n[{self._salvageHotkey.Key}] Salvage Parts"

        caller.SetTooltipText(result)
        return False


    @Hook("WillowGame.StatusMenuInventoryPanelGFxObject.EquipInputKey")
    def _equipInputKey(
        self,
        caller: UObject,
        function: UFunction,
        params: FStruct,
    ) -> bool:

        if params.uevent != KeybindManager.InputEvent.Pressed:
            return True

        if caller.bInitialSetupFinished is False:
            return True

        if caller.bInEquippedView is True:
            return True
        
        if params.ukey == self._salvageHotkey.Key:
            firstItem = caller.EquippingThing
            secondItem = caller.GetSelectedThing()
            if secondItem == None:
                return True
            if firstItem.Class.Name == "WillowWeapon" and firstItem.AmmoPool.PoolManager != None:
                self.UserInterface.equippedAttachError()
                return True
            elif firstItem.Class.Name != "WillowWeapon" and firstItem.IsEquipped():
                self.UserInterface.equippedAttachError()
                return True
            if firstItem == secondItem:
                return True
            
            if self.StrictUniques.CurrentValue and firstItem.Class.Name != "WillowClassMod" and firstItem.RarityLevel >= 5 and \
                firstItem.DefinitionData.BalanceDefinition != secondItem.DefinitionData.BalanceDefinition:
                    self.UserInterface.showStrictUniques()
            
            elif self.RarityLock.CurrentValue and \
                self.Globals.GetRarityForLevel(secondItem.RarityLevel if secondItem.RarityLevel != 500 else 501) < \
                self.Globals.GetRarityForLevel(firstItem.RarityLevel if firstItem.RarityLevel != 500 else 501):
                    self.UserInterface.showRarityLock(firstItem.RarityLevel)
            else:
                self.caller = caller
                self.UserInterface.selectInventoryItems(firstItem, secondItem)
                self.UserInterface.showUI()
            return False

        return True

    def InspectCustomItem(self, inspectableItem):
        self.caller.StartEquipPanel.InspectItem(inspectableItem)
    
    def EscapeCompareMenu(self):
        self.caller.EquipInputKey(0, 'Escape', 0)
        self.caller.EquipInputKey(0, 'Escape', 1)
    


class SparePartsUI():
    def __init__(self, owner) -> None:
        self.inspecting = False
        self.owner = owner
        self.PartsList = [[ #Weapon Parts
            ("Accessory1PartData", "Accessory1PartDefinition"),
            ("Accessory2PartData", "Accessory2PartDefinition"),
            ("BarrelPartData", "BarrelPartDefinition"),
            ("BodyPartData", "BodyPartDefinition"),
            ("ElementalPartData", "ElementalPartDefinition"),
            ("GripPartData", "GripPartDefinition"),
            ("SightPartData", "SightPartDefinition"),
            ("StockPartData", "StockPartDefinition"),
        ],[ #Item Parts
            ("AlphaParts", "AlphaPartData", "AlphaItemPartDefinition"),
            ("BetaParts", "BetaPartData", "BetaItemPartDefinition"),
            ("GammaParts", "GammaPartData", "GammaItemPartDefinition"),
            ("DeltaParts", "DeltaPartData", "DeltaItemPartDefinition"),
            ("EpsilonParts", "EpsilonPartData", "EpsilonItemPartDefinition"),
            ("ZetaParts", "ZetaPartData", "ZetaItemPartDefinition"),
            ("EtaParts", "EtaPartData", "EtaItemPartDefinition"),
            ("ThetaParts", "ThetaPartData", "ThetaItemPartDefinition"),
            ("MaterialParts", "MaterialPartData", "MaterialItemPartDefinition")
        ]]
        self.Rarities = [
            "<font color='#ffffff'>Common</font>",
            "<font color='#3dd20b'>Uncommon</font>",
            "<font color='#3c8dff'>Rare</font>",
            "<font color='#a83fe5'>Epic</font>",
            "<font color='#ca00a8'>E-Tech</font>",
            "<font color='#ffb300'>Legendary</font>",
            "<font color='#00ffff'>Pearlescent</font>",
            "<font color='#ff9ab8'>Seraph</font>",
            "<font color='#ff7570'>Effervescent</font>"
        ]


    def get_available_parts(self, attr: FStruct) -> list:
        return [x.Part for x in attr] if attr else []  

    def getRarityRankFromLevel(self, rarityLevel):
        if rarityLevel == 2:
            return (1, 1, 24)
        elif rarityLevel == 3:
            return (2, 2, 34)
        elif rarityLevel == 4:
            return (3, 3, 7)
        elif rarityLevel == 6:
            return (4, 3, 7)
        elif rarityLevel >= 7 and rarityLevel <= 10:
            return (5, 5, 18)
        elif rarityLevel == 500:
            return (6, 6, 29)
        elif rarityLevel == 501:
            return (7, 6, 29)
        elif rarityLevel == 506:
            return (8, 8, 48)

    def showRarityLock(self, firstItemRarityLevel):
        acceptableRarities = ""
        rarityRank = self.getRarityRankFromLevel(firstItemRarityLevel)
        i = 0
        for rarity in self.Rarities[rarityRank[1]:]: 
            acceptableRarities += rarity + ", "
            if i == 4 and rarityRank[0] == 1 or i == 3 and rarityRank[0] == 2:
                acceptableRarities += "\n".ljust(30)
            i += 1
        
        TrainingBox("<font color='#dc4646'>Rarity Lock</font>",
            "\n\n" + "You can't attach parts from an item of lower rarity\n".rjust(65) \
            + "than the one selected\n\n".rjust(63) \
            + f"{self.Rarities[rarityRank[0]]} rarity can accept parts from:\n".rjust(93) \
            + ' ' * rarityRank[2] + f"{acceptableRarities[:-2]}\n\n" \
            + "<font color=\"#708090\">This can be disabled in the mod options section</font>".rjust(93)).Show()


    def showStrictUniques(self):
        TrainingBox("<font color=\"#dc4646\">Strict Uniques</font>",
            "\n\n\n" + "You can't attach parts to a unique item that don't come\n".rjust(65) \
            + "from another copy of the same unique item\n\n\n".rjust(65) \
            + "<font color=\"#708090\">This can be disabled in the mod options section</font>".rjust(93)).Show()
    
    
    def equippedAttachError(self):
        TrainingBox("<font color=\"#dc4646\">Equipped Item</font>",
            "\n\n\n" + "You can't attach parts to an item you have equipped\n".rjust(65) \
            + "try unequipping it and trying again\n\n\n".rjust(69)).Show()


    def selectInventoryItems(self, firstItem, secondItem):
        self.swappableParts = []
        self.incompatibleParts = []
        self.guidedBoxButtons = []
        self.firstItem = firstItem
        self.secondItem = secondItem
        self.combinedItem = firstItem.CreateClone()

        if firstItem.Class.Name == "WillowWeapon":
            for part in self.PartsList[0]:
                firstItemPart = getattr(firstItem.DefinitionData, part[1])
                if firstItemPart is None:
                    continue
                secondItemPart = getattr(secondItem.DefinitionData, part[1])
                if secondItemPart is None:
                    continue
                if self.owner.SanityCheckSafeguard.CurrentValue == "Insane" and \
                    firstItem.DefinitionData.WeaponTypeDefinition.WeaponType == secondItem.DefinitionData.WeaponTypeDefinition.WeaponType or \
                    secondItemPart in self.get_available_parts(
                        getattr(
                            getattr(
                                firstItem.DefinitionData.BalanceDefinition.RuntimePartListCollection,
                                part[0]
                            ),
                            "WeightedParts")
                        ):
                            self.swappableParts.append([firstItemPart, secondItemPart, part[1], 0])
                else:
                    self.incompatibleParts.append(secondItemPart)

        else:
            if firstItem.Class.Name == "WillowShield":
                i = 0
                j = 4
                partLookup = ["InventoryDefinition", 0]
                
            elif firstItem.Class.Name == "WillowArtifact":
                i = 0 if self.owner.SanityCheckSafeguard.CurrentValue != "Safe" else 7
                j = 8
                partLookup = ["PartListCollection", 1]
            
            elif firstItem.Class.Name == "WillowClassMod":
                i = 0 if self.owner.SanityCheckSafeguard.CurrentValue != "Safe" else 1
                j = 9
                partLookup = ["RuntimePartListCollection", 1]
                
            elif firstItem.Class.Name == "WillowGrenadeMod":
                i = 0
                j = 8
                partLookup = ["PartListCollection", 1]
            
            for part in self.PartsList[1][i:j]:
                firstItemPart = getattr(firstItem.DefinitionData, part[2])
                if firstItemPart is None:
                    continue
                secondItemPart = getattr(secondItem.DefinitionData, part[2])
                if secondItemPart is None:
                    continue
                if self.owner.SanityCheckSafeguard.CurrentValue == "Insane" or secondItemPart in self.get_available_parts(
                    getattr(
                        getattr(
                            getattr(
                                firstItem.DefinitionData.BalanceDefinition,
                                partLookup[0]
                            ),
                            part[partLookup[1]]),
                        "WeightedParts")
                    ):
                    self.swappableParts.append([firstItemPart, secondItemPart, part[2], 0])
                else:
                    self.incompatibleParts.append(secondItemPart)

    
    def replacePart(self, selectedBox: OptionBoxButton):
        partLocation = self.swappableParts[self.guidedBoxButtons.index(selectedBox)]
        partLocation[3] = 1 - partLocation[3]
        setattr(self.combinedItem.DefinitionData, partLocation[2], partLocation[partLocation[3]])
        self.combinedItem.InitializeInternal(True)
        self.showGuidedReplacements(self.guidedBoxButtons.index(selectedBox))

    
    def confirmGuidedReplacements(self, key, event):
        if event == KeybindManager.InputEvent.Pressed:
            if key == self.owner._salvageHotkey.Key:
                self.GuidedBox.Hide()
                
                inventory_manager: UObject = GetEngine().GamePlayers[0].Actor.GetPawnInventoryManager()
                inventory_manager.AddInventoryToBackpack(self.combinedItem.CreateClone())
                inventory_manager.RemoveInventoryFromBackpack(self.firstItem)
                inventory_manager.RemoveInventoryFromBackpack(self.secondItem)
                
                self.owner.EscapeCompareMenu()

            if key == "F":
                self.inspecting = True
                self.owner.InspectCustomItem(self.combinedItem.CreateClone())
                self.GuidedBox.Hide()
        
    
    def showGuidedReplacements(self, selectedButtonIndex: int = 0):
        GuidedBoxCaption = ""
        GuidedBoxCaptionList = []
        self.guidedBoxButtons.clear()
        for parts in self.swappableParts:
            partName = re.sub("<(\/){0,1}font( color=(\"|\')#[0-z]{6}(\"|\')){0,1}>", "", get_single_part_name(parts[1 - parts[3]], True, False))
            self.guidedBoxButtons.append(OptionBoxButton(f"Salvage {partName}"))
            GuidedBoxCaptionList.append(f"<font color=\"#ffe6cc\">  {get_single_part_name(parts[parts[3]], True, False)}</font>")
        
        if len(self.swappableParts) <= 5:
            for Caption in GuidedBoxCaptionList:
                GuidedBoxCaption += Caption + "\n"
        else:
            i = 0
            while i < len(self.swappableParts) - 5:
                GuidedBoxCaption += GuidedBoxCaptionList[i].ljust(70) + GuidedBoxCaptionList[i+5] + "\n"
                i += 1
            for Caption in GuidedBoxCaptionList[i:5]:
                GuidedBoxCaption += Caption + "\n"
        
        self.GuidedBox = OptionBox(Title = "Current Parts", Caption = GuidedBoxCaption, Buttons = self.guidedBoxButtons,
            Tooltip = f"[Enter] Select    [Escape] Cancel    [{self.owner._salvageHotkey.Key}] Confirm    [F] Inspect")
        self.GuidedBox.OnInput = self.confirmGuidedReplacements
        self.GuidedBox.OnPress = self.replacePart
        self.GuidedBox.Show(self.guidedBoxButtons[selectedButtonIndex])
    
    
    def showUI(self):
        foundPartsPopupCaption = "<font color=\"#35fc3d\">Compatible:</font>\n"
        for parts in self.swappableParts[:]:
            foundPartsPopupCaption += f"    {get_single_part_name(parts[1], True, False)}"
            if parts[0] == parts[1]:
                foundPartsPopupCaption += "  <font color=\"#708090\">DUPLICATE PART</font>"
                self.swappableParts.remove(parts)
            foundPartsPopupCaption += "\n"
        
        if len(self.incompatibleParts) > 0 :
            foundPartsPopupCaption += "\n<font color=\"#dc4646\">Incompatible:</font>\n"
            for part in self.incompatibleParts:
                foundPartsPopupCaption += f"    {get_single_part_name(part, True, True)}\n"
        
        if self.firstItem.Class.Name == "WillowClassMod" and \
            self.firstItem.DefinitionData.ItemDefinition.RequiredPlayerClass != self.secondItem.DefinitionData.ItemDefinition.RequiredPlayerClass:
            TrainingBox("<font color=\"#dc4646\">Incompatible Class Mod</font>",
                "\n\n\n" + "Can't salvage parts from another classes' Class Mod".rjust(63)).Show()
        else:
            foundPartsPopup = TrainingBox(f"Found Parts [{self.owner.SanityCheckSafeguard.CurrentValue} Mode]", foundPartsPopupCaption)
            if len(self.swappableParts) > 0 :
                foundPartsPopup.OnExit = self.showGuidedReplacements
            foundPartsPopup.Show()


instance = SpareParts()

if __name__ == "__main__":
    Log(f"[{instance.Name}] Manually loaded")
    for mod in Mods:
        if mod.Name == instance.Name:
            if mod.IsEnabled:
                mod.Disable()
            Mods.remove(mod)
            Log(f"[{instance.Name}] Removed last instance")

            # Fixes inspect.getfile()
            instance.__class__.__module__ = mod.__class__.__module__
            break

RegisterMod(instance)
