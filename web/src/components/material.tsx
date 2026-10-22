/* Adapt Material Design 3 web components for React client rendering.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import * as React from "react";
import { createComponent } from "@lit/react";
import { MdOutlinedTextField } from "@material/web/textfield/outlined-text-field.js";
import { MdFilledButton } from "@material/web/button/filled-button.js";
import { MdCircularProgress } from "@material/web/progress/circular-progress.js";

export const TextField = createComponent({
  react: React,
  tagName: "md-outlined-text-field",
  elementClass: MdOutlinedTextField,
});

export const FilledButton = createComponent({
  react: React,
  tagName: "md-filled-button",
  elementClass: MdFilledButton,
});

export const CircularProgress = createComponent({
  react: React,
  tagName: "md-circular-progress",
  elementClass: MdCircularProgress,
});
