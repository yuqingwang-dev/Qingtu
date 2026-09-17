import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import type { NextAuthOptions } from "next-auth";

const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        try {
          // Call our backend to create/update user and get JWT token
          const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/google`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              google_id: account.providerAccountId,
              email: user.email,
              name: user.name,
              avatar_url: user.image,
            }),
          });

          if (response.ok) {
            const data = await response.json();
            // Store the JWT token in the user object (will be available in jwt callback)
            (user as any).accessToken = data.access_token;
            (user as any).userId = data.user.id;
            return true;
          }
        } catch (error) {
          console.error("Error authenticating with backend:", error);
          // Don't block sign-in if backend is temporarily unreachable
          return true;
        }
      }
      return true;
    },
    async jwt({ token, user, account }) {
      // Initial sign in
      if (user) {
        token.accessToken = (user as any).accessToken;
        token.userId = (user as any).userId;
      }
      return token;
    },
    async session({ session, token }) {
      // Add custom fields to session
      (session as any).accessToken = token.accessToken;
      (session as any).userId = token.userId;
      return session;
    },
  },
  pages: {
    signIn: "/",  // Redirect to home page for sign in
  },
  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
