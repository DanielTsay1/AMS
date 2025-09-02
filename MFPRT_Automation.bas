Option Explicit

' SolidWorks MFPRT Automation Macro
' Automates saving selected (or detected) concept parts as sequential MFPRT parts,
' updates Description property, saves to MFPRT Series folders, and updates
' assembly references.
'
' Usage:
' - Open the final assembly.
' - Select components to convert (recommended), or leave no selection to auto-detect candidates.
' - Run: MFPRT_Run
'
' Configuration:
' - Adjust CONST values below to match your environment.

' =====================
' Configuration
' =====================
Private Const MFPRT_ROOT As String = "N:\\Manufactured Parts\\MFPRT Series"  ' Root folder containing MFPRT buckets
Private Const MFPRT_SUFFIX As String = "MFPRT"                                  ' Suffix appended to the number
Private Const MFPRT_NUM_WIDTH As Integer = 5                                      ' e.g., 5 -> 00001MFPRT
Private Const FILE_EXT As String = ".SLDPRT"

' If True, macro will only process selected components in the active assembly tree
Private Const ONLY_PROCESS_SELECTED As Boolean = True

' If True, prompt for description for each part; otherwise keep existing
Private Const PROMPT_FOR_DESCRIPTION As Boolean = True

' =====================
' SolidWorks globals
' =====================
Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2
Dim swAssy As SldWorks.AssemblyDoc

Public Sub MFPRT_Run()
	On Error GoTo EH

	Set swApp = Application.SldWorks
	If swApp Is Nothing Then
		MsgBox "SolidWorks is not available.", vbCritical
		Exit Sub
	End If

	Set swModel = swApp.ActiveDoc
	If swModel Is Nothing Then
		MsgBox "Open an assembly and try again.", vbExclamation
		Exit Sub
	End If
	If swModel.GetType <> swDocASSEMBLY Then
		MsgBox "Active document is not an assembly.", vbExclamation
		Exit Sub
	End If

	Set swAssy = swModel

	Dim componentsToProcess As Collection
	Set componentsToProcess = GetTargetComponents(swAssy)

	If componentsToProcess Is Nothing Or componentsToProcess.Count = 0 Then
		MsgBox "No components to process.", vbInformation
		Exit Sub
	End If

	Dim processedCount As Long
	processedCount = 0

	Dim comp As SldWorks.Component2
	For Each comp In componentsToProcess
		If ProcessSingleComponent(comp) Then
			processedCount = processedCount + 1
		End If
	Next comp

	' Rebuild and save the assembly at the end
	swModel.EditRebuild3
	swModel.Save3 swSaveAsOptions_Silent, 0, 0

	MsgBox CStr(processedCount) & " component(s) processed.", vbInformation
	Exit Sub

EH:
	MsgBox "Error: " & Err.Number & " - " & Err.Description, vbCritical
End Sub

' Returns a collection of Component2 to process
Private Function GetTargetComponents(ByVal assemblyDoc As SldWorks.AssemblyDoc) As Collection
	Dim targets As New Collection

	Dim selectionMgr As SldWorks.SelectionMgr
	Set selectionMgr = swModel.SelectionManager

	Dim hasSelection As Boolean
	hasSelection = (Not selectionMgr Is Nothing And selectionMgr.GetSelectedObjectCount2(-1) > 0)

	If ONLY_PROCESS_SELECTED And hasSelection Then
		Dim i As Long
		For i = 1 To selectionMgr.GetSelectedObjectCount2(-1)
			If selectionMgr.GetSelectedObjectType3(i, -1) = swSelCOMPONENTS Then
				Dim selComp As SldWorks.Component2
				Set selComp = selectionMgr.GetSelectedObjectsComponent3(i, -1)
				If IsValidConceptPart(selComp) Then
					targets.Add selComp
				End If
			End If
		Next i
	Else
		' Auto-detect candidate concept parts across the assembly tree
		Dim rootComps As Variant
		rootComps = assemblyDoc.GetComponents(True) ' recursive

		If Not IsEmpty(rootComps) Then
			Dim idx As Long
			For idx = LBound(rootComps) To UBound(rootComps)
				Dim comp As SldWorks.Component2
				Set comp = rootComps(idx)
				If IsValidConceptPart(comp) Then
					targets.Add comp
				End If
			Next idx
		End If
	End If

	Set GetTargetComponents = targets
End Function

' Determines if a component is a leaf, resolved, non-virtual part that does NOT already match the MFPRT naming pattern
Private Function IsValidConceptPart(ByVal comp As SldWorks.Component2) As Boolean
	On Error Resume Next
	IsValidConceptPart = False
	If comp Is Nothing Then Exit Function
	If comp.IsSuppressed Then Exit Function

	Dim model As SldWorks.ModelDoc2
	Set model = comp.GetModelDoc2
	If model Is Nothing Then Exit Function
	If model.GetType <> swDocPART Then Exit Function

	If comp.IsVirtual Then Exit Function

	Dim path As String
	path = comp.GetPathName
	If Len(path) = 0 Then Exit Function
	If LCase$(Right$(path, 7)) <> LCase$(FILE_EXT) Then Exit Function

	Dim fileName As String
	fileName = GetFileNameWithoutExtension(path)
	
	' Already MFPRT-named? Expect pattern: #####MFPRT
	If IsLikeMFPRTName(fileName) Then Exit Function

	IsValidConceptPart = True
End Function

Private Function IsLikeMFPRTName(ByVal baseName As String) As Boolean
	Dim expectedSuffix As String
	expectedSuffix = MFPRT_SUFFIX
	If Len(baseName) < Len(expectedSuffix) + MFPRT_NUM_WIDTH Then
		IsLikeMFPRTName = False
		Exit Function
	End If
	Dim suffixPart As String
	suffixPart = Right$(baseName, Len(expectedSuffix))
	If StrComp(UCase$(suffixPart), UCase$(expectedSuffix), vbBinaryCompare) <> 0 Then
		IsLikeMFPRTName = False
		Exit Function
	End If
	Dim numberPart As String
	numberPart = Mid$(baseName, Len(baseName) - Len(expectedSuffix) - MFPRT_NUM_WIDTH + 1, MFPRT_NUM_WIDTH)
	IsLikeMFPRTName = IsNumeric(numberPart)
End Function

Private Function GetFileNameWithoutExtension(ByVal fullPath As String) As String
	Dim pos As Long
	pos = InStrRev(fullPath, ".")
	If pos > 0 Then
		GetFileNameWithoutExtension = Mid$(fullPath, InStrRev(fullPath, "\\") + 1, pos - InStrRev(fullPath, "\\") - 1)
	Else
		GetFileNameWithoutExtension = Mid$(fullPath, InStrRev(fullPath, "\\") + 1)
	End If
End Function

' Process a single component: save as MFPRT and update assembly reference
Private Function ProcessSingleComponent(ByVal comp As SldWorks.Component2) As Boolean
	On Error GoTo EH
	ProcessSingleComponent = False

	Dim partModel As SldWorks.ModelDoc2
	Set partModel = comp.GetModelDoc2
	If partModel Is Nothing Then Exit Function

	Dim oldPath As String
	oldPath = comp.GetPathName
	If Len(oldPath) = 0 Then Exit Function

	Dim currentDescription As String
	currentDescription = GetCustomPropertyValue(partModel, "Description")

	Dim newDescription As String
	If PROMPT_FOR_DESCRIPTION Then
		newDescription = InputBox("Enter description for new MFPRT part:" & vbCrLf & GetFileNameWithoutExtension(oldPath), _
			"MFPRT Description", IIf(Len(currentDescription) > 0, currentDescription, ""))
		If StrPtr(newDescription) = 0 Then ' Cancel pressed
			Exit Function
		End If
	Else
		newDescription = currentDescription
	End If

	Dim nextNumber As Long
	nextNumber = GetNextMFPRTNumber()
	If nextNumber <= 0 Then
		MsgBox "Unable to determine next MFPRT number.", vbExclamation
		Exit Function
	End If

	Dim newBaseName As String
	newBaseName = Format$(nextNumber, String$(MFPRT_NUM_WIDTH, "0")) & MFPRT_SUFFIX

	Dim targetFolder As String
	targetFolder = ResolveTargetBucketFolder(nextNumber)
	If Len(targetFolder) = 0 Then
		targetFolder = MFPRT_ROOT
	End If
	If Right$(targetFolder, 1) <> "\\" Then targetFolder = targetFolder & "\\"

	Dim newFullPath As String
	newFullPath = targetFolder & newBaseName & FILE_EXT

	If FileExists(newFullPath) Then
		MsgBox "Target file already exists: " & newFullPath, vbCritical
		Exit Function
	End If

	' Update description before saving
	If Len(newDescription) > 0 Then
		SetCustomPropertyValue partModel, "Description", newDescription
	End If

	' Save As to the new MFPRT path
	Dim saveOk As Boolean
	saveOk = partModel.SaveAs3(newFullPath, swSaveAsOptions_Silent, 0)
	If Not saveOk Then
		MsgBox "Failed to save part as: " & newFullPath, vbCritical
		Exit Function
	End If

	' Update assembly reference from old path to new path
	On Error Resume Next
	comp.SetPathName newFullPath
	If Err.Number <> 0 Then
		Err.Clear
		Dim ext As SldWorks.ModelDocExtension
		Set ext = swModel.Extension
		If Not ext Is Nothing Then
			ext.ReplaceReferences oldPath, newFullPath
		End If
	End If
	On Error GoTo EH

	ProcessSingleComponent = True
	Exit Function

EH:
	MsgBox "Error processing component: " & Err.Number & " - " & Err.Description, vbCritical
End Function

Private Function GetCustomPropertyValue(ByVal model As SldWorks.ModelDoc2, ByVal propName As String) As String
	On Error Resume Next
	Dim mgr As SldWorks.CustomPropertyManager
	Set mgr = model.Extension.CustomPropertyManager("")
	Dim valueOut As String
	Dim rc As Long
	rc = mgr.Get2(propName, valueOut)
	If rc = 0 Then
		GetCustomPropertyValue = valueOut
	Else
		GetCustomPropertyValue = ""
	End If
End Function

Private Sub SetCustomPropertyValue(ByVal model As SldWorks.ModelDoc2, ByVal propName As String, ByVal propValue As String)
	On Error Resume Next
	Dim mgr As SldWorks.CustomPropertyManager
	Set mgr = model.Extension.CustomPropertyManager("")
	mgr.Add3 propName, swCustomInfoText, propValue, swCustomPropertyAddOption_e.swCustomPropertyReplaceValue
End Sub

' Determine next available MFPRT number by scanning all files under MFPRT_ROOT
Private Function GetNextMFPRTNumber() As Long
	Dim fso As Object
	Set fso = CreateObject("Scripting.FileSystemObject")
	If Not fso.FolderExists(MFPRT_ROOT) Then
		GetNextMFPRTNumber = -1
		Exit Function
	End If

	Dim maxNumber As Long
	maxNumber = 0

	Dim root As Object
	Set root = fso.GetFolder(MFPRT_ROOT)

	' Scan files in root
	maxNumber = MaxNumberInFolder(root, maxNumber)

	' Scan subfolders
	Dim subf As Object
	For Each subf In root.SubFolders
		maxNumber = MaxNumberInFolder(subf, maxNumber)
	Next subf

	GetNextMFPRTNumber = maxNumber + 1
End Function

' Return the highest MFPRT number found in a folder (non-recursive)
Private Function MaxNumberInFolder(ByVal folderObj As Object, ByVal currentMax As Long) As Long
	Dim f As Object
	For Each f In folderObj.Files
		If LCase$(Right$(f.Name, 7)) = LCase$(FILE_EXT) Then
			Dim baseName As String
			baseName = Left$(f.Name, Len(f.Name) - Len(FILE_EXT))
			Dim num As Long
			num = ParseMFPRTNumber(baseName)
			If num > currentMax Then currentMax = num
		End If
	Next f
	MaxNumberInFolder = currentMax
End Function

' Parse baseName like 00001MFPRT -> 1; returns 0 if not match
Private Function ParseMFPRTNumber(ByVal baseName As String) As Long
	If Not IsLikeMFPRTName(baseName) Then
		ParseMFPRTNumber = 0
		Exit Function
	End If
	Dim numberPart As String
	numberPart = Left$(baseName, MFPRT_NUM_WIDTH)
	ParseMFPRTNumber = CLng(numberPart)
End Function

' Determine which bucket folder to save into based on next number.
' Strategy: use the folder that currently contains the highest-numbered MFPRT file.
' If none found, fall back to MFPRT_ROOT.
Private Function ResolveTargetBucketFolder(ByVal nextNumber As Long) As String
	Dim fso As Object
	Set fso = CreateObject("Scripting.FileSystemObject")
	If Not fso.FolderExists(MFPRT_ROOT) Then
		ResolveTargetBucketFolder = ""
		Exit Function
	End If

	Dim root As Object
	Set root = fso.GetFolder(MFPRT_ROOT)

	Dim bestFolder As String
	bestFolder = ""
	Dim bestNum As Long
	bestNum = 0

	Dim f As Object
	For Each f In root.Files
		If LCase$(Right$(f.Name, 7)) = LCase$(FILE_EXT) Then
			Dim bn As String
			bn = Left$(f.Name, Len(f.Name) - Len(FILE_EXT))
			Dim n As Long
			n = ParseMFPRTNumber(bn)
			If n > bestNum Then
				bestNum = n
				bestFolder = root.Path
			End If
		End If
	Next f

	Dim subf As Object
	For Each subf In root.SubFolders
		Dim ff As Object
		For Each ff In subf.Files
			If LCase$(Right$(ff.Name, 7)) = LCase$(FILE_EXT) Then
				Dim bn2 As String
				bn2 = Left$(ff.Name, Len(ff.Name) - Len(FILE_EXT))
				Dim n2 As Long
				n2 = ParseMFPRTNumber(bn2)
				If n2 > bestNum Then
					bestNum = n2
					bestFolder = subf.Path
				End If
			End If
		Next ff
	Next subf

	If Len(bestFolder) = 0 Then
		bestFolder = root.Path
	End If

	ResolveTargetBucketFolder = bestFolder
End Function

Private Function FileExists(ByVal fullPath As String) As Boolean
	On Error Resume Next
	Dim fso As Object
	Set fso = CreateObject("Scripting.FileSystemObject")
	FileExists = fso.FileExists(fullPath)
End Function