assert __import__("mods_base").__version_info__ >= (1, 12), "Please update the SDK"
assert __import__("unrealsdk").__version_info__ >= (3, 2, 0), "Please update the SDK"
assert __import__("ui_utils").__version_info__ >= (1, 5), "Please update the SDK"

import importlib
import re
import webbrowser
from collections.abc import Callable
from types import ModuleType
from typing import Any

import unrealsdk
from unrealsdk import logging
from unrealsdk.hooks import Block, Type, Unset, prevent_hooking_direct_calls
from unrealsdk.unreal import BoundFunction, UObject, WrappedArray, WrappedStruct

from mods_base import (BoolOption, CoopSupport, EInputEvent, Game, HiddenOption, KeybindType, SpinnerOption,
                       build_mod, get_ordered_mod_list, get_pc, hook)
from ui_utils import OptionBox, OptionBoxButton, TrainingBox

# Python Part Notifier is still a legacy mod, so it has to be imported and called under legacy compat.
# If either legacy compat or Python Part Notifier is unavailable, raw part names are used instead.
PPN_VERSION: str = "1.9"
PythonPartNotifier: ModuleType | None = None
get_single_part_name: Callable[[UObject, bool, bool], str] | None = None

try:
    from legacy_compat import ENABLED as LEGACY_COMPAT_ENABLED
except ImportError:
    LEGACY_COMPAT_ENABLED = False

if LEGACY_COMPAT_ENABLED:
    from legacy_compat import legacy_compat
    try:
        with legacy_compat():
            PythonPartNotifier = importlib.import_module("Mods.PythonPartNotifier")
    except ModuleNotFoundError:
        # Opens PPN's page rather than the mod DB's requirements page, which can't link to legacy mods
        webbrowser.open("https://bl-sdk.github.io/willow2-mod-db/mods/pythonpartnotifier/")
        raise

    if getattr(getattr(PythonPartNotifier, "instance", None), "Version", None) == PPN_VERSION:
        get_single_part_name = PythonPartNotifier.get_single_part_name
    else:
        logging.warning(f"[Spare Parts] Python Part Notifier v{PPN_VERSION} not found, using raw part names")
else:
    logging.warning("[Spare Parts] Legacy compat is unavailable so Python Part Notifier can't be used, "
                    "using raw part names")


def get_part_name(part: UObject, show_slot: bool, show_type: bool) -> str:
    if get_single_part_name is None:
        return part.Name
    from legacy_compat import legacy_compat
    with legacy_compat():
        return get_single_part_name(part, show_slot, show_type)


SANITY_SAVER_URL: str = "https://bl-sdk.github.io/willow2-mod-db/mods/sanitysaver/"


def isSanitySaverEnabled() -> bool:
    return any(otherMod.name == "Sanity Saver" and otherMod.is_enabled for otherMod in get_ordered_mod_list())


def needsInsaneWarning() -> bool:
    return not InsaneWarningAcknowledged.value and not isSanitySaverEnabled()


def showInsaneWarning(resetValue: str, inOptionsMenu: bool, onKeep: Callable[[], None] | None = None) -> None:
    openPageButton = OptionBoxButton("Open Sanity Saver Page")
    keepButton = OptionBoxButton("I Know What I'm Doing")

    def onSelect(box: OptionBox, button: OptionBoxButton) -> None:
        if button == openPageButton:
            webbrowser.open(SANITY_SAVER_URL)
            box.show(openPageButton)
        else:
            InsaneWarningAcknowledged.value = True
            InsaneWarningAcknowledged.save()
            if onKeep is not None:
                onKeep()

    def onCancel(box: OptionBox) -> None:
        SanityCheckSafeguard.value = resetValue
        if not inOptionsMenu:
            mod.save_settings()
        message: str = "\n\n\n\n" + f"Sanity Check Safeguard has been set back to {resetValue}\n\n\n".rjust(66)
        if inOptionsMenu:
            message += "<font color=\"#708090\">The options menu will show Insane until you reopen it</font>".rjust(95)
        TrainingBox(title="<font color=\"#dc4646\">Sanity Check Safeguard Reset</font>", message=message).show()

    OptionBox(
        title="<font color=\"#dc4646\">Sanity Saver Not Found</font>",
        message="\n\n\n" + "Items made in Insane mode can fail the sanity check.\n".rjust(67)
        + "They will be deleted when your save next loads,\n".rjust(66)
        + "unless Sanity Saver is installed and enabled.".rjust(67),
        buttons=[openPageButton, keepButton],
        on_select=onSelect,
        on_cancel=onCancel
    ).show()


def warnInsaneWithoutSanitySaver(option: SpinnerOption, newValue: str) -> None:
    if newValue == "Insane" and needsInsaneWarning():
        showInsaneWarning(option.value, True)


salvageHotkey: KeybindType = KeybindType(
    "Salvage Item Parts",
    "C",
    lambda: None,
)

RarityLock = BoolOption(
    identifier="Rarity Lock",
    description="Only allow salvaging parts from items of the same or higher rarity.",
    value=True,
    true_text="On",
    false_text="Off"
)
StrictUniques = BoolOption(
    identifier="Strict Uniques",
    description=("Unique items can only salvage parts from the same unique items.\t"
                 "E.g. An Unkempt Harold can only salvage parts from another Unkempt Harold."),
    value=True,
    true_text="On",
    false_text="Off"
)
SanityCheckSafeguard = SpinnerOption(
    identifier="Sanity Check Safeguard",
    description=("Safe: Every part combination will pass the sanity check.\n"
                 "Expert: Extra potentially unsafe Relic and COM parts.\n"
                 "Insane: Removes all checks and safeguards."),
    value="Safe",
    choices=["Safe", "Expert", "Insane"],
    on_change_while_enabled=warnInsaneWithoutSanitySaver
)
SwapMethod = SpinnerOption(
    identifier="Parts Transfer Method",
    description=("Regular: Destroy an item to salvage its parts.\n"
                 "Swap: Exchange parts between items keeping both."),
    value="Regular",
    choices=["Regular", "Swap"]
)
InsaneWarningAcknowledged = HiddenOption(
    identifier="Insane Warning Acknowledged",
    value=False
)

inventoryPanel: UObject | None = None


@hook("WillowGame.ItemInspectionGFxMovie:OnClose")
def _inspectOnClose(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    if UserInterface.inspecting:
        UserInterface.inspecting = False
        UserInterface.showGuidedReplacements()


pendingHint: str | None = None


@hook("WillowGame.StatusMenuExGFxMovie:SetInventoryTooltipsText")
def _startInventoryTooltips(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:

    global pendingHint
    panel: UObject | None = obj.InventoryPanel

    if panel is None or panel.bInEquippedView is True:
        return

    if panel.bIsDoingEquip is False:
        return

    if panel.EquippingThing == panel.GetSelectedThing():
        return

    action: str = "Swap" if SwapMethod.value == "Swap" else "Salvage"
    pendingHint = f"[{salvageHotkey.key}] {action} Parts"
    _addSalvageHint.enable()


@hook("WillowGame.StatusMenuExGFxMovie:SetInventoryTooltipsText", Type.POST_UNCONDITIONAL)
def _endInventoryTooltips(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    global pendingHint
    pendingHint = None
    _addSalvageHint.disable()


@hook("GFxUI.GFxMoviePlayer:ResolveDataStoreMarkup")
def _addSalvageHint(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> tuple[type[Block], str] | None:
    global pendingHint
    if pendingHint is None:
        return None

    markup: str
    if ret is Unset:
        with prevent_hooking_direct_calls():
            markup = func(args)
    else:
        markup = ret

    # If another mod already added its own line, join it rather than adding a third
    result = markup + ("    " if "\n" in markup else "\n") + pendingHint
    pendingHint = None
    return Block, result


@hook("WillowGame.StatusMenuInventoryPanelGFxObject:EquipInputKey")
def _equipInputKey(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> type[Block] | None:

    if args.uevent != EInputEvent.IE_Pressed:
        return None

    if obj.bInitialSetupFinished is False:
        return None

    if obj.bInEquippedView is True:
        return None

    if args.ukey == salvageHotkey.key:
        firstItem: UObject = obj.EquippingThing
        secondItem: UObject = obj.GetSelectedThing()
        if secondItem is None:
            return None
        if firstItem.Class.Name == "WillowWeapon" and firstItem.AmmoPool.PoolManager is not None:
            UserInterface.equippedAttachError()
            return None
        elif firstItem.Class.Name != "WillowWeapon" and firstItem.IsEquipped():
            UserInterface.equippedAttachError()
            return None
        if firstItem == secondItem:
            return None

        if SanityCheckSafeguard.value == "Insane" and needsInsaneWarning():
            showInsaneWarning(SanityCheckSafeguard.default_value, False,
                              lambda: startSalvage(obj, firstItem, secondItem))
        else:
            startSalvage(obj, firstItem, secondItem)
        return Block

    return None


def startSalvage(panel: UObject, firstItem: UObject, secondItem: UObject) -> None:
    global inventoryPanel

    # Swapping moves parts in both directions, so both locks have to hold both ways
    swapMode: bool = SwapMethod.value == "Swap"
    firstRarity: int = getRarity(firstItem)
    secondRarity: int = getRarity(secondItem)

    if StrictUniques.value and firstItem.Class.Name != "WillowClassMod" \
        and (firstRarity >= 5 or swapMode and secondRarity >= 5) \
            and firstItem.DefinitionData.BalanceDefinition != secondItem.DefinitionData.BalanceDefinition:
        UserInterface.showStrictUniques()

    elif RarityLock.value and (secondRarity < firstRarity or swapMode and firstRarity < secondRarity):
        UserInterface.showRarityLock(firstItem.RarityLevel, swapMode)
    else:
        inventoryPanel = panel
        UserInterface.selectInventoryItems(firstItem, secondItem)
        UserInterface.showUI()


def getRarity(item: UObject) -> int:
    globalsDefinition: UObject = unrealsdk.find_object("GlobalsDefinition", "GD_Globals.General.Globals")
    return globalsDefinition.GetRarityForLevel(item.RarityLevel if item.RarityLevel != 500 else 501)


def InspectCustomItem(inspectableItem: UObject) -> None:
    assert inventoryPanel is not None
    inventoryPanel.StartEquipPanel.InspectItem(inspectableItem)


def EscapeCompareMenu() -> None:
    assert inventoryPanel is not None
    inventoryPanel.EquipInputKey(0, 'Escape', 0)
    inventoryPanel.EquipInputKey(0, 'Escape', 1)


class SparePartsUI():
    def __init__(self) -> None:
        self.inspecting = False
        self.PartsList: list[list[tuple[str, str, str]]] = [[  # Weapon Parts
            ("Accessory1PartData", "Accessory1PartDefinition", ""),
            ("Accessory2PartData", "Accessory2PartDefinition", ""),
            ("BarrelPartData", "BarrelPartDefinition", ""),
            ("BodyPartData", "BodyPartDefinition", ""),
            ("ElementalPartData", "ElementalPartDefinition", ""),
            ("GripPartData", "GripPartDefinition", ""),
            ("SightPartData", "SightPartDefinition", ""),
            ("StockPartData", "StockPartDefinition", ""),
            ("MaterialPartData", "MaterialPartDefinition", "")
        ], [  # Item Parts
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
        self.BL2Rarities: list[str] = [
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
        self.TPSRarities: list[str] = [
            "<font color='#ffffff'>Common</font>",
            "<font color='#3dd20b'>Uncommon</font>",
            "<font color='#3c8dff'>Rare</font>",
            "<font color='#a83fe5'>Epic</font>",
            "<font color='#ca00a8'>E-Tech</font>",
            "<font color='#ffb300'>Legendary</font>",
            "<font color='#ffa4e7'>Glitch</font>"
        ]

    def get_available_parts(self, attr: WrappedArray) -> list:
        return [x.Part for x in attr] if attr else []

    def get_balance_parts(self, item: UObject, partLookup: tuple[str, int], part: tuple[str, str, str]) -> list:
        return self.get_available_parts(
            getattr(
                getattr(
                    getattr(
                        item.DefinitionData.BalanceDefinition,
                        partLookup[0]
                    ),
                    part[partLookup[1]]
                ),
                "WeightedParts"
            )
        )

    def getShieldPartLookup(self, shield: UObject) -> tuple[str, int]:
        """
        A couple shields use PartListCollection instead of InventoryDefinition, but still have a valid
        AlphaParts declared under InventoryDefinition. This check just reroutes those edge cases.
        """
        if shield.DefinitionData.BalanceDefinition.InventoryDefinition.BetaParts is not None:
            return ("InventoryDefinition", 0)
        return ("PartListCollection", 1)

    def getRarityRankFromLevel(self, rarityLevel: int) -> tuple[int, int, int]:
        if rarityLevel == 2:
            return (1, 1, 24)
        elif rarityLevel == 3:
            return (2, 2, 34)
        elif Game.get_current() == Game.BL2:
            if rarityLevel == 4:
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
        elif Game.get_current() == Game.TPS:
            if rarityLevel == 4:
                return (3, 3, 38)
            elif rarityLevel == 6:
                return (4, 3, 38)
            elif rarityLevel >= 7 and rarityLevel <= 10:
                return (5, 5, 50)
            elif rarityLevel == 501:
                return (9, 6, 60)
        return (9, 6, 60)

    def showRarityLock(self, firstItemRarityLevel: int, swapMode: bool = False) -> None:
        if swapMode:
            TrainingBox(title="<font color='#dc4646'>Rarity Lock</font>",
                        message="\n\n\n" + "You can only swap parts between items\n".rjust(64)
                        + "of the same rarity\n\n\n".rjust(64)
                        + "<font color=\"#708090\">This can be disabled in the mod options section</font>".rjust(93)
                        ).show()
            return

        acceptableRarities: str = ""
        rarityRank: tuple[int, int, int] = self.getRarityRankFromLevel(firstItemRarityLevel)
        i = 0
        if Game.get_current() == Game.BL2:
            leftPadRarities = f"{self.BL2Rarities[rarityRank[0]]} rarity can accept parts from:\n".rjust(93) \
                + ' ' * (rarityRank[2])
            for rarity in self.BL2Rarities[rarityRank[1]:]:
                acceptableRarities += rarity + ", "
                if i == 4 and rarityRank[0] == 1 or i == 3 and rarityRank[0] == 2:
                    acceptableRarities += "\n".ljust(30)
                i += 1
        else:
            leftPadRarities = f"{self.TPSRarities[rarityRank[0]]} rarity can accept parts from:\n".rjust(93) \
                + ' ' * (rarityRank[2] - 6)
            for rarity in self.TPSRarities[rarityRank[1]:]:
                acceptableRarities += rarity + ", "
                i += 1

        TrainingBox(title="<font color='#dc4646'>Rarity Lock</font>",
                    message="\n\n" + "You can't attach parts from an item of lower rarity\n".rjust(65)
                    + "than the one selected\n\n".rjust(63)
                    + leftPadRarities + f"{acceptableRarities[:-2]}\n\n"
                    + "<font color=\"#708090\">This can be disabled in the mod options section</font>".rjust(93)).show()

    def showStrictUniques(self):
        TrainingBox(title="<font color=\"#dc4646\">Strict Uniques</font>",
                    message="\n\n\n" + "You can't attach parts to a unique item that don't come\n".rjust(65)
                    + "from another copy of the same unique item\n\n\n".rjust(65)
                    + "<font color=\"#708090\">This can be disabled in the mod options section</font>".rjust(93)).show()

    def equippedAttachError(self):
        TrainingBox(title="<font color=\"#dc4646\">Equipped Item</font>",
                    message="\n\n\n" + "You can't attach parts to an item you have equipped\n".rjust(65)
                    + "try unequipping it and trying again\n\n\n".rjust(69)).show()

    def selectInventoryItems(self, firstItem: UObject, secondItem: UObject):
        self.swappableParts: list = []
        self.incompatibleParts: list = []
        self.guidedBoxButtons: list[OptionBoxButton] = []
        self.firstItem: UObject = firstItem
        self.secondItem: UObject = secondItem
        self.combinedItem: UObject = firstItem.CreateClone()
        self.swapMode: bool = SwapMethod.value == "Swap"
        if self.swapMode:
            self.combinedSecondItem: UObject = secondItem.CreateClone()

        if firstItem.Class.Name == "WillowWeapon":
            i = 9 if SanityCheckSafeguard.value == "Insane" else 8
            for part in self.PartsList[0][0:i]:
                firstItemPart: UObject = getattr(firstItem.DefinitionData, part[1])
                secondItemPart: UObject = getattr(secondItem.DefinitionData, part[1])
                if SanityCheckSafeguard.value == "Insane":
                    if firstItemPart is None and secondItemPart is None:
                        continue
                else:
                    if secondItemPart is None:
                        continue
                    if firstItemPart is None:
                        self.incompatibleParts.append(secondItemPart)
                        continue

                if SanityCheckSafeguard.value == "Insane" \
                    and firstItem.DefinitionData.WeaponTypeDefinition.WeaponType == \
                        secondItem.DefinitionData.WeaponTypeDefinition.WeaponType \
                        or secondItemPart in self.get_balance_parts(firstItem, ("RuntimePartListCollection", 0), part) \
                        and (not self.swapMode or firstItemPart in self.get_balance_parts(
                            secondItem, ("RuntimePartListCollection", 0), part)):
                    self.swappableParts.append([firstItemPart, secondItemPart, part[1], 0])
                else:
                    self.incompatibleParts.append(secondItemPart)

        else:
            extraParts: list[tuple[str, str, str]] = []
            if firstItem.Class.Name == "WillowShield":
                i = 0
                j = 4
                # Shields never use Epsilon-Theta, so Insane only adds Material
                if SanityCheckSafeguard.value == "Insane":
                    extraParts = [self.PartsList[1][8]]
                partLookup: tuple[str, int] = self.getShieldPartLookup(firstItem)

            elif firstItem.Class.Name == "WillowArtifact":
                i = 0 if SanityCheckSafeguard.value != "Safe" else 7
                j = 9 if SanityCheckSafeguard.value == "Insane" else 8
                partLookup = ("PartListCollection", 1)

            elif firstItem.Class.Name == "WillowClassMod":
                i = 0 if SanityCheckSafeguard.value != "Safe" else 1
                j = 9
                partLookup = ("RuntimePartListCollection", 1)

            elif firstItem.Class.Name == "WillowGrenadeMod":
                i = 0
                j = 9 if SanityCheckSafeguard.value == "Insane" else 8
                partLookup = ("PartListCollection", 1)

            else:
                return

            secondPartLookup: tuple[str, int] = self.getShieldPartLookup(secondItem) \
                if firstItem.Class.Name == "WillowShield" else partLookup

            for part in self.PartsList[1][i:j] + extraParts:
                firstItemPart = getattr(firstItem.DefinitionData, part[2])
                if firstItemPart is None:
                    continue
                secondItemPart = getattr(secondItem.DefinitionData, part[2])
                if secondItemPart is None:
                    continue
                if SanityCheckSafeguard.value == "Insane" \
                    or secondItemPart in self.get_balance_parts(firstItem, partLookup, part) \
                        and (not self.swapMode
                             or firstItemPart in self.get_balance_parts(secondItem, secondPartLookup, part)):
                    self.swappableParts.append([firstItemPart, secondItemPart, part[2], 0])
                else:
                    self.incompatibleParts.append(secondItemPart)

    def replacePart(self, box: OptionBox, button: OptionBoxButton):
        partLocation: list = self.swappableParts[self.guidedBoxButtons.index(button)]
        partLocation[3] = 1 - partLocation[3]
        setattr(self.combinedItem.DefinitionData, partLocation[2], partLocation[partLocation[3]])
        self.combinedItem.InitializeInternal(True)
        if self.swapMode:
            setattr(self.combinedSecondItem.DefinitionData, partLocation[2], partLocation[1 - partLocation[3]])
            self.combinedSecondItem.InitializeInternal(True)
        self.showGuidedReplacements(self.guidedBoxButtons.index(button))

    def confirmGuidedReplacements(self, box: OptionBox, key: str, event: EInputEvent) -> None:
        if event == EInputEvent.IE_Pressed:
            if key == salvageHotkey.key:
                box.hide()

                inventory_manager: UObject = get_pc().GetPawnInventoryManager()
                self.combinedItem.DefinitionData.UniqueId = self.combinedItem.GenerateUniqueID()
                firstClone: UObject = self.combinedItem.CreateClone()
                firstClone.SetMark(self.firstItem.GetMark())
                inventory_manager.AddBackpackInventory(firstClone)
                if self.swapMode:
                    self.combinedSecondItem.DefinitionData.UniqueId = self.combinedSecondItem.GenerateUniqueID()
                    secondClone: UObject = self.combinedSecondItem.CreateClone()
                    secondClone.SetMark(self.secondItem.GetMark())
                    inventory_manager.AddBackpackInventory(secondClone)
                inventory_manager.RemoveInventoryFromBackpack(self.firstItem)
                inventory_manager.RemoveInventoryFromBackpack(self.secondItem)
                inventory_manager.UpdateBackpackInventoryCount()

                EscapeCompareMenu()

            if key == "F":
                self.inspecting = True
                InspectCustomItem(self.combinedItem.CreateClone())
                box.hide()

            if self.swapMode and key == "G":
                self.inspecting = True
                InspectCustomItem(self.combinedSecondItem.CreateClone())
                box.hide()

    def showGuidedReplacements(self, selectedButtonIndex: int = 0):
        GuidedBoxCaption: str = ""
        GuidedBoxCaptionList: list[str] = []
        self.guidedBoxButtons.clear()
        partname: str
        for parts in self.swappableParts:
            if parts[1 - parts[3]] is None:
                partName = re.sub(
                    r"<(\/){0,1}font( color=(\"|\')#[0-z]{6}(\"|\')){0,1}>",
                    "",
                    get_part_name(parts[parts[3]], True, False)
                )
                partName = "No " + re.sub(".* ", "", partName)
            else:
                partName = re.sub(
                    r"<(\/){0,1}font( color=(\"|\')#[0-z]{6}(\"|\')){0,1}>",
                    "",
                    get_part_name(parts[1 - parts[3]], True, False)
                )
            self.guidedBoxButtons.append(OptionBoxButton(f"{'Swap' if self.swapMode else 'Salvage'} {partName}"))
            if parts[parts[3]] is None:
                partName = re.sub(
                    r"<(\/){0,1}font( color=(\"|\')#[0-z]{6}(\"|\')){0,1}>",
                    "",
                    get_part_name(parts[1 - parts[3]], True, False)
                )
                partname = "No " + re.sub(".* ", "", partName)
                GuidedBoxCaptionList.append(
                    f"<font color=\"#ffe6cc\">  {partname}</font>"
                )
            else:
                GuidedBoxCaptionList.append(
                    f"<font color=\"#ffe6cc\">  {get_part_name(parts[parts[3]], True, False)}</font>"
                )

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

        OptionBox(
            title="Current Parts",
            message=GuidedBoxCaption,
            tooltip=f"[Enter] Select    [Escape] Cancel    [{salvageHotkey.key}] Confirm    "
            + ("[F/G] Inspect" if self.swapMode else "[F] Inspect"),
            buttons=self.guidedBoxButtons,
            on_select=self.replacePart,
            on_input=self.confirmGuidedReplacements
        ).show(self.guidedBoxButtons[selectedButtonIndex])

    def showUI(self):
        foundPartsPopupCaption: str = "<font color=\"#35fc3d\">Compatible:</font>\n"
        for parts in self.swappableParts[:]:
            if parts[1] is not None:
                foundPartsPopupCaption += f"    {get_part_name(parts[1], True, False)}"
                if parts[0] == parts[1]:
                    foundPartsPopupCaption += "  <font color=\"#708090\">DUPLICATE PART</font>"
                    self.swappableParts.remove(parts)
                foundPartsPopupCaption += "\n"

        if len(self.incompatibleParts) > 0:
            foundPartsPopupCaption += "\n<font color=\"#dc4646\">Incompatible:</font>\n"
            for part in self.incompatibleParts:
                if part is not None:
                    foundPartsPopupCaption += f"    {get_part_name(part, True, True)}\n"

        if self.firstItem.Class.Name == "WillowClassMod" \
            and SanityCheckSafeguard.value != "Insane" \
                and self.firstItem.DefinitionData.ItemDefinition.RequiredPlayerClass != \
                self.secondItem.DefinitionData.ItemDefinition.RequiredPlayerClass:
            TrainingBox(title="<font color=\"#dc4646\">Incompatible Class Mod</font>",
                        message="\n\n\n" + "Can't salvage parts from another classes' Class Mod".rjust(63)).show()
        else:
            foundPartsPopup = TrainingBox(
                title=f"Found Parts [{SanityCheckSafeguard.value} Mode]", message=foundPartsPopupCaption
            )
            if len(self.swappableParts) > 0:
                foundPartsPopup.on_exit = lambda _: self.showGuidedReplacements()
            foundPartsPopup.show()


UserInterface = SparePartsUI()

mod = build_mod(
    coop_support=CoopSupport.ClientSide if Game.get_current() == Game.BL2 else CoopSupport.Incompatible,
    keybinds=[salvageHotkey],
    options=[RarityLock, StrictUniques, SanityCheckSafeguard, SwapMethod, InsaneWarningAcknowledged],
    hooks=[_inspectOnClose, _startInventoryTooltips, _endInventoryTooltips, _equipInputKey],
    on_disable=_addSalvageHint.disable
)
mod.description = "<font size='26' color='#de5b00'>\t     Spare Parts</font>\n\n" + mod.description
