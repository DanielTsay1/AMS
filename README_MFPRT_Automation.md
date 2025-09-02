### MFPRT Automation Macro (SolidWorks VBA)

This macro automates converting concept parts in an assembly into sequentially numbered MFPRT parts, saving them into your MFPRT Series folders, prompting for Description, and updating references in the open assembly.

### Files
- `MFPRT_Automation.bas`: VBA module. Import into SolidWorks macro editor.

### Configuration
Edit constants at the top of `MFPRT_Automation.bas`:
- `MFPRT_ROOT`: `N:\Manufactured Parts\MFPRT Series`
- `MFPRT_SUFFIX`: `MFPRT`
- `MFPRT_NUM_WIDTH`: 5 (produces names like `00001MFPRT.SLDPRT`)

Buckets are automatically detected by scanning subfolders; the macro saves new parts into the folder containing the highest-numbered part found, or the root if none exist.

### Usage
1. Open your final assembly in SolidWorks.
2. Optionally select the components you want to convert (recommended). If you select none, the macro will auto-detect parts that are not already named as MFPRTs.
3. Run macro subroutine `MFPRT_Run`.
4. For each part, you will be prompted to confirm or enter the Description custom property.
5. The macro saves the part as the next sequential MFPRT in the appropriate folder and updates the assembly reference.

### Notes
- Concept detection is conservative: leaf, resolved, non-virtual parts whose filenames don’t already match `#####MFPRT`. Adjust `IsValidConceptPart` if you have other criteria (e.g., property flags, naming).
- Numbering scans all `.SLDPRT` files in `MFPRT_ROOT` and direct subfolders and assigns next number = (max found + 1).
- Reference update tries `Component2.SetPathName` first, then falls back to `ModelDocExtension.ReplaceReferences` for robustness. Assembly rebuild and save are performed at the end.
- Always test on a copy first.

### Installation
- SolidWorks: Tools → Macro → New… or Edit… → import `MFPRT_Automation.bas`.
- Ensure `Microsoft Scripting Runtime` is allowed (the macro uses FileSystemObject via late-binding, so no explicit reference is required).

### Troubleshooting
- If no components are processed, verify selection mode or relax `ONLY_PROCESS_SELECTED` in the constants.
- If numbering is wrong, verify that existing MFPRT file names follow `#####MFPRT.SLDPRT`.
- If replacement fails, ensure write access to the assembly location and that the new path is reachable.