import { BarChart3, Home, KanbanSquare, Mail, Settings, Share2, Wallet } from "lucide-react";
import { Navigate, Route, Routes } from "react-router";

import { CataloguePage } from "@/features/catalogue/CataloguePage";
import { HealthPage } from "@/features/health/HealthPage";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { AreaPlaceholder } from "@/features/placeholder/AreaPlaceholder";
import { SignInPage } from "@/features/auth/SignInPage";
import { SignUpPage } from "@/features/auth/SignUpPage";

import { AppShell } from "./AppShell";
import { HomeRedirect, RedirectIfAuthed, RequireAuth } from "./guards";

export function App() {
  return (
    <Routes>
      <Route index element={<HomeRedirect />} />
      <Route
        path="sign-in"
        element={
          <RedirectIfAuthed>
            <SignInPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="sign-up"
        element={
          <RedirectIfAuthed>
            <SignUpPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="onboarding"
        element={
          <RequireAuth>
            <OnboardingPage />
          </RequireAuth>
        }
      />
      <Route
        path="o/:orgId/p/:projectId"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        {/* Until something is connected, the catalogue IS the project's home. */}
        <Route index element={<Navigate to="integrations" replace />} />
        <Route path="integrations" element={<CataloguePage />} />
        <Route
          path="home"
          element={<AreaPlaceholder icon={Home} titleKey="nav.home" bodyKey="placeholder.home" />}
        />
        <Route path="health" element={<HealthPage />} />
        <Route
          path="social"
          element={
            <AreaPlaceholder icon={Share2} titleKey="nav.social" bodyKey="placeholder.social" />
          }
        />
        <Route
          path="email"
          element={<AreaPlaceholder icon={Mail} titleKey="nav.email" bodyKey="placeholder.email" />}
        />
        <Route
          path="analytics"
          element={
            <AreaPlaceholder
              icon={BarChart3}
              titleKey="nav.analytics"
              bodyKey="placeholder.analytics"
            />
          }
        />
        <Route
          path="money"
          element={
            <AreaPlaceholder icon={Wallet} titleKey="nav.money" bodyKey="placeholder.money" />
          }
        />
        <Route
          path="board"
          element={
            <AreaPlaceholder icon={KanbanSquare} titleKey="nav.board" bodyKey="placeholder.board" />
          }
        />
        <Route
          path="settings"
          element={
            <AreaPlaceholder
              icon={Settings}
              titleKey="nav.settings"
              bodyKey="placeholder.settings"
            />
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
