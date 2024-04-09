import json
import re
import webbrowser
import unrealsdk

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
    webbrowser.open("https://bl-sdk.github.io/requirements/?mod=SpareParts&UserFeedback&Python%20Part%20Notifier")
    raise


class SpareParts(SDKMod):
    Name: str = "Spare Parts"
    Author: str = "LaryIsland"
    Description: str = "<font size='26' color='#de5b00'>Spare Parts</font>\n\n" \
        "Allows you to salvage parts from items and attach them to other items.\n\n" \
        "Just select an item from your backpack, hover over another item " \
        "and press the 'salvage' hotkey. Default is [C]\n\n" \
        "Note: the item you salvage parts from will be destroyed in the process."
    Version: str = "1.0"

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
        
        self.RarityLock = Options.Boolean(
            Caption="Rarity Lock",
            Description="Only allow salvaging parts from items of the same or higher rarity.",
            StartingValue=True,
            Choices=["Off", "On"]  # False, True
        )
        self.StrictUniques = Options.Boolean(
            Caption="Strict Uniques",
            Description="Unique items can only salvage parts from the same unique items.\t" \
                "E.g. An Unkempt Harold can only salvage parts from another Unkempt Harold.",
            StartingValue=True,
            Choices=["Off", "On"]  # False, True
        )
        self.ExpertMode = Options.Boolean(
            Caption="Expert Mode",
            Description="Enabled salvaging extra Relic and COM parts.\n" \
                "WARNING if you don't know what you're doing you can create items that will be deleted by the sanity check.",
            StartingValue=False,
            Choices=["Off", "On"]  # False, True
        )
        
        self.Options = [
            self.RarityLock,
            self.StrictUniques,
            self.ExpertMode,
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
        caller: unrealsdk.UObject,
        function: unrealsdk.UFunction,
        params: unrealsdk.FStruct,
    ) -> bool:
        if self.UserInterface.inspecting:
            self.UserInterface.inspecting = False
            self.UserInterface.showGuidedReplacements()
        return True
    
    
    @Hook("WillowGame.StatusMenuInventoryPanelGFxObject.SetTooltipText")
    def _setTooltipText(
        self,
        caller: unrealsdk.UObject,
        function: unrealsdk.UFunction,
        params: unrealsdk.FStruct,
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
        caller: unrealsdk.UObject,
        function: unrealsdk.UFunction,
        params: unrealsdk.FStruct,
    ) -> bool:

        if params.uevent != KeybindManager.InputEvent.Pressed:
            return True

        if caller.bInitialSetupFinished is False:
            return True

        if caller.bInEquippedView is True:
            return True
        
        if params.ukey == self._salvageHotkey.Key:
            if caller.EquippingThing == caller.GetSelectedThing():
                return True
            
            if self.StrictUniques.CurrentValue and caller.EquippingThing.Class.Name != "WillowClassMod" and caller.EquippingThing.RarityLevel >= 5 and \
                caller.EquippingThing.DefinitionData.BalanceDefinition != caller.GetSelectedThing().DefinitionData.BalanceDefinition:
                self.UserInterface.showStrictUniques()
            elif self.RarityLock.CurrentValue and caller.GetSelectedThing().RarityLevel < caller.EquippingThing.RarityLevel:
                self.UserInterface.showRarityLock()
            else:
                self.UserInterface.selectInventoryItems(caller.EquippingThing, caller.GetSelectedThing())
                self.UserInterface.showUI()
            self.caller = caller
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


    def get_available_parts(self, attr: unrealsdk.FStruct) -> list:
        return [x.Part for x in attr] if attr else []  


    def showRarityLock(self):
        TrainingBox("<font color='#dc4646'>Rarity Lock</font>",
            "\n\n\n              You can't attach parts from an item of lower rarity\n" \
            "                                        than the one selected\n\n\n" \
            "                  <font color=\"#708090\">This can be disabled in the mod options section</font>").Show()


    def showStrictUniques(self):
        TrainingBox("<font color=\"#dc4646\">Strict Uniques</font>",
            "\n\n\n          You can't attach parts to a unique item that don't come\n" \
            "                      from another copy of the same unique item\n\n\n" \
            "                  <font color=\"#708090\">This can be disabled in the mod options section</font>").Show()


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
                if secondItemPart in self.get_available_parts(
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
                i = 0 if self.owner.ExpertMode.CurrentValue else 7
                j = 8
                partLookup = ["PartListCollection", 1]
            
            elif firstItem.Class.Name == "WillowClassMod":
                i = 0 if self.owner.ExpertMode.CurrentValue else 1
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
                if secondItemPart in self.get_available_parts(
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
                
                inventory_manager: unrealsdk.UObject = unrealsdk.GetEngine().GamePlayers[0].Actor.GetPawnInventoryManager()
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
        self.guidedBoxButtons.clear()
        i = 0
        for parts in self.swappableParts:
            partName = re.sub("<(\/){0,1}font( color=(\"|\')#[0-z]{6}(\"|\')){0,1}>", "", get_single_part_name(parts[1 - parts[3]], True, False))
            self.guidedBoxButtons.append(OptionBoxButton(f"Salvage {partName}"))
            GuidedBoxCaption += f"<font color=\"#ffe6cc\">  {get_single_part_name(parts[parts[3]], True, False)}\n</font>"
        
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
                "\n\n\n            Can't salvage parts from another classes' Class Mod").Show()
        else:
            foundPartsPopup = TrainingBox("Found Parts", foundPartsPopupCaption)
            if len(self.swappableParts) > 0 :
                foundPartsPopup.OnExit = self.showGuidedReplacements
            foundPartsPopup.Show()


instance = SpareParts()

if __name__ == "__main__":
    unrealsdk.Log(f"[{instance.Name}] Manually loaded")
    for mod in Mods:
        if mod.Name == instance.Name:
            if mod.IsEnabled:
                mod.Disable()
            Mods.remove(mod)
            unrealsdk.Log(f"[{instance.Name}] Removed last instance")

            # Fixes inspect.getfile()
            instance.__class__.__module__ = mod.__class__.__module__
            break

RegisterMod(instance)
