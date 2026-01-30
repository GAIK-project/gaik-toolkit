"use client";

import Lottie from "lottie-react";
import animationData from "@/components/animations/lottie/success-animation.json";

export function SuccessAnimation() {
  return (
    <div className="mx-auto flex h-24 w-24 items-center justify-center">
      <Lottie animationData={animationData} loop={false} />
    </div>
  );
}
