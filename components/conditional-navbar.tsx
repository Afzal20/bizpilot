"use client"

import { usePathname } from "next/navigation"
import Navbar from "@/components/navbar"

const dashboardRoutes = [
  "/dashboard",
  "/clients",
  "/products",
  "/invoices",
  "/team",
  "/settings",
  "/help",
  "/search",
  "/view",
]

export function ConditionalNavbar() {
  const pathname = usePathname()
  // Hide navbar on all dashboard routes
  const isDashboardRoute = dashboardRoutes.some(
    (route) => pathname?.startsWith(route)
  )

  if (isDashboardRoute) {
    return null
  }

  return <Navbar />
}

